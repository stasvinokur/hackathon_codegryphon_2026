from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

# ── regex patterns ──────────────────────────────────────────────────────────
DATE_RE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
TIME_RE = re.compile(r"\d{2}:\d{2}:\d{2}")
_AMT_DOT_DECIMAL = re.compile(r"(?P<amount>-?\d{1,3}(?:,\d{3})*\.\d{2})")
_AMT_COMMA_DECIMAL = re.compile(r"(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})")


def _match_amount(text: str) -> re.Match[str] | None:
    return _AMT_DOT_DECIMAL.search(text) or _AMT_COMMA_DECIMAL.search(text)
CURRENCY_RE = re.compile(r"\b(RUB|RUR|USD|EUR|₽)\b", re.IGNORECASE)
PAGE_HEADER_RE = re.compile(
    r"^(Проведена|Обработана|В валюте|Поступление|Расход|Комиссия|Задолжен-?|ность|Описание|операции)$"
)

# ── metadata patterns ───────────────────────────────────────────────────────
CARD_NUMBER_RE = re.compile(r"Номер карты\s+([\d*]+)")
PERIOD_RE = re.compile(r"Период выписки\s+(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})")
CREDIT_LIMIT_RE = re.compile(r"Кредитный лимит\s+([\d\s,\.]+)\s*(?:RUB|RUR)?")
AVAILABLE_BALANCE_RE = re.compile(r"Доступный остаток\s+([\d\s,\.\-]+)\s*(?:RUB|RUR)?")
DEBT_TOTAL_RE = re.compile(r"Общая сумма задолженности\*?\s+([\d\s,\.]+)")
MIN_PAYMENT_RE = re.compile(r"Минимальный платеж\s+([\d\s,\.]+)\s*(?:RUB|RUR)?")
GRACE_STATUS_RE = re.compile(r"Статус беспроцентного периода\s+(.+)")


def _parse_decimal(raw_value: str) -> Decimal:
    normalized = raw_value.replace(" ", "")
    if "." in normalized and "," in normalized:
        # 3,000.00 → commas are thousands separators
        normalized = normalized.replace(",", "")
    elif "," in normalized:
        # 500,00 → comma is decimal separator
        normalized = normalized.replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y")
    except ValueError:
        return None


def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str.strip()} {time_str.strip()}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        return _parse_date(date_str)


def _extract_merchant(description: str) -> str:
    """Extract merchant name from the cleaned description."""
    cleaned = re.sub(r"Оплата\s+товаров\s+и\s+услуг\.?\s*", "", description, flags=re.IGNORECASE).strip()
    cleaned = cleaned.lstrip(". ")
    if cleaned:
        return cleaned
    tokens = [t for t in re.split(r"\s+", description.strip()) if t]
    return " ".join(tokens[:4]) if tokens else "UNKNOWN"


def _is_numeric_filler(line: str) -> bool:
    """Return True if the line is a standalone number, currency, or debt fragment."""
    stripped = line.replace(",", "").replace(".", "").replace(" ", "").replace("-", "")
    if CURRENCY_RE.fullmatch(line.strip()):
        return True
    return stripped.isdigit() and len(line) < 15


def _is_description_trigger(line: str) -> bool:
    """Return True if the line signals the start of a description."""
    return "Оплата" in line or "OOO" in line or "MVIDEO" in line


def _settlement_lag(posted_at: datetime | None, processed_at: datetime | None) -> Decimal:
    if posted_at and processed_at and processed_at > posted_at:
        delta: timedelta = processed_at - posted_at
        return Decimal(str(round(delta.total_seconds() / 3600, 2)))
    return Decimal("0")


class StatementPdfParser:
    """Template-aware parser for VTB card statement PDF text."""

    def _extract_lines(self, path: Path) -> list[str]:
        lines: list[str] = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    lines.extend(line.strip() for line in text.splitlines() if line.strip())
        except Exception:
            text = path.read_bytes().decode("utf-8", errors="ignore")
            lines.extend(line.strip() for line in text.splitlines() if line.strip())
        return lines

    # ── metadata ────────────────────────────────────────────────────────────

    def extract_metadata(self, lines: list[str]) -> dict:
        """Extract statement-level metadata from header lines."""
        full_text = "\n".join(lines)
        metadata: dict = {"bank_name": "ВТБ", "product_type": "Кредитная карта"}

        _simple_patterns: list[tuple[re.Pattern[str], str, bool]] = [
            (CARD_NUMBER_RE, "masked_card_number", False),
            (CREDIT_LIMIT_RE, "credit_limit", True),
            (AVAILABLE_BALANCE_RE, "available_balance", True),
            (DEBT_TOTAL_RE, "debt_total", True),
            (MIN_PAYMENT_RE, "minimum_payment", True),
        ]
        for pattern, key, as_decimal in _simple_patterns:
            m = pattern.search(full_text)
            if m:
                metadata[key] = _parse_decimal(m.group(1)) if as_decimal else m.group(1)

        m = PERIOD_RE.search(full_text)
        if m:
            metadata["statement_period_start"] = _parse_date(m.group(1))
            metadata["statement_period_end"] = _parse_date(m.group(2))

        m = GRACE_STATUS_RE.search(full_text)
        if m:
            metadata["grace_period_status"] = m.group(1).strip()

        return metadata

    # ── segmentation ────────────────────────────────────────────────────────

    @staticmethod
    def _is_page_header(line: str) -> bool:
        return bool(PAGE_HEADER_RE.match(line)) or "Операции по карте" in line or "Операции в обработке" in line

    def _find_tx_section_start(self, lines: list[str]) -> int:
        for i, line in enumerate(lines):
            if "Проведена" in line and "Обработана" in line:
                return i + 1
        return 0

    def _should_skip_line(self, line: str) -> bool:
        return self._is_page_header(line) or bool(re.fullmatch(r"\d{1,3}", line))

    def _segment_transaction_blocks(self, lines: list[str]) -> list[list[str]]:
        """Split lines into transaction blocks. Each transaction starts with a date."""
        tx_start = self._find_tx_section_start(lines)
        blocks: list[list[str]] = []
        current: list[str] = []

        for line in lines[tx_start:]:
            if self._should_skip_line(line):
                continue

            is_date = bool(DATE_RE.fullmatch(line))
            if not is_date:
                if current:
                    current.append(line)
                continue

            if not current:
                current = [line]
                continue

            date_count = sum(1 for bl in current if DATE_RE.fullmatch(bl))
            if date_count < 2:
                current.append(line)
            else:
                blocks.append(current)
                current = [line]

        if current:
            blocks.append(current)
        return blocks

    # ── block parsing ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_fragment(pending: str, line: str, amounts: list[Decimal]) -> str | None:
        """Try to complete a split debt number. Returns remaining fragment or None."""
        stripped = line.strip()
        if stripped.isdigit() and len(stripped) <= 3:
            amounts.append(_parse_decimal(pending + stripped))
            return None
        amounts.append(_parse_decimal(pending))
        return None

    @staticmethod
    def _try_partial(line: str) -> str | None:
        """Check if line is a partial number like '867,198.1' (split debt value)."""
        partial = re.fullmatch(r"(-?\d{1,3}(?:[,.]\d{3})*\.\d)", line.strip())
        return partial.group(1) if partial else None

    @staticmethod
    def _extract_currency(line: str, current: str) -> str:
        cm = CURRENCY_RE.search(line)
        if not cm:
            return current
        cur = cm.group(1).upper().replace("₽", "RUB")
        return "RUB" if cur == "RUR" else cur

    def _collect_structural(
        self, block: list[str],
    ) -> tuple[list[str], list[str], list[Decimal], str]:
        """First pass: collect dates, times, all amounts, and currency.

        Amounts order in VTB format:
          0 = signed transaction amount, 1 = inflow, 2 = outflow,
          3 = fee, 4 = debt_after_transaction.
        """
        dates: list[str] = []
        times: list[str] = []
        amounts: list[Decimal] = []
        currency = "RUB"
        pending_fragment: str | None = None

        for line in block:
            if DATE_RE.fullmatch(line):
                dates.append(line)
                continue
            if TIME_RE.fullmatch(line):
                times.append(line)
                continue
            currency = self._extract_currency(line, currency)

            if pending_fragment is not None:
                self._resolve_fragment(pending_fragment, line, amounts)
                pending_fragment = None
                continue

            am = _match_amount(line)
            if am:
                amounts.append(_parse_decimal(am.group("amount")))
            elif not CURRENCY_RE.fullmatch(line.strip()):
                pending_fragment = self._try_partial(line)

        if pending_fragment is not None:
            amounts.append(_parse_decimal(pending_fragment))

        return dates, times, amounts, currency

    @staticmethod
    def _extract_desc_from_composite(line: str) -> str:
        """Extract description tail from a line that mixes amounts and text."""
        matches = list(_AMT_DOT_DECIMAL.finditer(line)) + list(_AMT_COMMA_DECIMAL.finditer(line))
        if not matches:
            return line
        last_end = max(m.end() for m in matches)
        tail = line[last_end:].strip()
        # strip residual currency codes
        tail = re.sub(r"^(?:RUB|RUR|USD|EUR|₽)\s*", "", tail).strip()
        return tail

    def _classify_line(self, line: str, in_desc: bool) -> tuple[str | None, bool]:
        """Classify a block line and return (text_to_append | None, new_in_desc)."""
        if DATE_RE.fullmatch(line) or TIME_RE.fullmatch(line):
            return None, in_desc
        has_amounts = bool(_match_amount(line))
        if has_amounts:
            tail = self._extract_desc_from_composite(line)
            if tail and len(tail) > 2:
                return tail, True
            return None, in_desc
        if _is_description_trigger(line):
            in_desc = True
        if in_desc and not _is_numeric_filler(line):
            return line, in_desc
        if not in_desc and not _is_numeric_filler(line) and len(line) > 2:
            return line, True
        return None, in_desc

    def _collect_description(self, block: list[str]) -> str:
        """Second pass: merge wrapped description lines."""
        parts: list[str] = []
        in_desc = False
        for line in block:
            text, in_desc = self._classify_line(line, in_desc)
            if text:
                parts.append(text)
        return " ".join(parts).strip()

    def _parse_block(self, block: list[str]) -> dict | None:
        dates, times, amounts, currency = self._collect_structural(block)
        if len(dates) < 2 or not amounts:
            return None

        amount = amounts[0]
        fee_amount = amounts[3] if len(amounts) > 3 else Decimal("0")
        debt_after = amounts[4] if len(amounts) > 4 else None

        posted_at = _parse_datetime(dates[0], times[0] if times else "00:00:00")
        processed_at = _parse_datetime(dates[1], times[1] if len(times) > 1 else "00:00:00")
        description = self._collect_description(block)
        is_credit = amount > 0

        return {
            "posted_at": posted_at,
            "processed_at": processed_at,
            "settlement_lag_hours": _settlement_lag(posted_at, processed_at),
            "amount_signed_original": amount,
            "currency_original": currency,
            "inflow_amount": amount if is_credit else Decimal("0"),
            "outflow_amount": abs(amount) if not is_credit else Decimal("0"),
            "fee_amount": fee_amount,
            "debt_after_transaction": debt_after,
            "description_raw": description,
            "description_clean": description,
            "merchant_raw": _extract_merchant(description),
            "is_credit": is_credit,
            "raw_row_json": {"lines": block},
        }

    # ── table-based extraction (primary for real PDFs) ─────────────────────

    @staticmethod
    def _parse_date_cell(cell: str) -> tuple[datetime | None, str]:
        """Parse a date+time cell like '14.07.2025\\n11:51:54'."""
        parts = cell.strip().split("\n")
        time_str = parts[1] if len(parts) > 1 else "00:00:00"
        return _parse_datetime(parts[0], time_str), parts[0]

    @staticmethod
    def _parse_amount_cell(cell: str) -> tuple[Decimal | None, str]:
        """Parse an amount cell, returning (amount, currency)."""
        text = (cell or "").replace("\n", " ")
        am = _match_amount(text)
        if not am:
            return None, "RUB"
        cm = CURRENCY_RE.search(text)
        currency = cm.group(1).upper() if cm else "RUB"
        return _parse_decimal(am.group("amount")), currency

    @staticmethod
    def _parse_numeric_cell(cell: str) -> Decimal | None:
        """Parse a numeric cell (fee or debt), returning Decimal or None."""
        text = (cell or "").replace("\n", "")
        am = _match_amount(text)
        return _parse_decimal(am.group("amount")) if am else None

    def _parse_table_row(self, row: list[str | None]) -> dict | None:
        """Parse a single table row from pdfplumber extract_tables()."""
        if not row or len(row) < 7:
            return None
        if not DATE_RE.search((row[0] or "")):
            return None

        posted_at, _ = self._parse_date_cell(row[0] or "")
        processed_at, _ = self._parse_date_cell(row[1] or "")
        amount, currency = self._parse_amount_cell(row[2] or "")
        if amount is None:
            return None

        fee_amount = self._parse_numeric_cell(row[5]) or Decimal("0")
        debt_after = self._parse_numeric_cell(row[6])
        description = (row[7] or "").replace("\n", " ").strip() if len(row) > 7 else ""
        is_credit = amount > 0

        return {
            "posted_at": posted_at,
            "processed_at": processed_at,
            "settlement_lag_hours": _settlement_lag(posted_at, processed_at),
            "amount_signed_original": amount,
            "currency_original": currency,
            "inflow_amount": amount if is_credit else Decimal("0"),
            "outflow_amount": abs(amount) if not is_credit else Decimal("0"),
            "fee_amount": fee_amount,
            "debt_after_transaction": debt_after,
            "description_raw": description,
            "description_clean": description,
            "merchant_raw": _extract_merchant(description),
            "is_credit": is_credit,
            "raw_row_json": {"cells": [c or "" for c in row]},
        }

    def _extract_from_tables(self, path: Path) -> list[dict]:
        """Extract transactions using pdfplumber table extraction."""
        results: list[dict] = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            parsed = self._parse_table_row(row)
                            if parsed:
                                results.append(parsed)
        except Exception:
            pass
        return results

    # ── public API ──────────────────────────────────────────────────────────

    def parse_transactions(self, file_path: str) -> list[dict]:
        path = Path(file_path)
        if not path.exists():
            return []
        # Try table extraction first (works with real PDFs)
        results = self._extract_from_tables(path)
        if results:
            return results
        # Fallback to text-based block parsing (for plain text files)
        lines = self._extract_lines(path)
        blocks = self._segment_transaction_blocks(lines)
        return [row for block in blocks if (row := self._parse_block(block)) is not None]

    def parse_statement_metadata(self, file_path: str) -> dict:
        """Parse only metadata from a statement PDF."""
        path = Path(file_path)
        if not path.exists():
            return {}
        return self.extract_metadata(self._extract_lines(path))

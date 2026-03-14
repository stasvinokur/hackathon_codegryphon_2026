from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher


@dataclass(slots=True)
class NormalizedMerchant:
    """Normalized merchant identity payload."""

    merchant_alias: str
    normalized_merchant_name: str
    merchant_family: str
    merchant_group: str
    confidence_score: Decimal
    alias_hash: str


# ── domain-style merchant grouping ──────────────────────────────────────────

_MERCHANT_FAMILIES: dict[str, str] = {
    "yandex": "YANDEX",
    "metro": "METRO",
    "ozon": "OZON",
    "nalog": "NALOG",
    "pik": "PIK",
    "mvideo": "MVIDEO",
    "vkusvill": "VKUSVILL",
    "sber": "SBERBANK",
    "npd": "NALOG",
    "gosuslugi": "GOSUSLUGI",
    "hostingvds": "HOSTING",
    "xorek": "HOSTING",
    "cloudx": "HOSTING",
    "ztv": "ZTV",
    "zetalink": "ZETALINK",
    "reg": "REG",
    "apteka": "PHARMACY",
    "gorzdrav": "PHARMACY",
    "transport": "TRANSPORT",
    "istudio": "APPLE",
    "restore": "APPLE",
    "gpudc": "HOSTING",
    "stimul": "STIMUL",
}


def _resolve_family(normalized: str) -> str:
    """Resolve merchant family using keyword matching."""
    lower = normalized.lower()
    for keyword, family in _MERCHANT_FAMILIES.items():
        if keyword in lower:
            return family
    parts = lower.split()
    return parts[0].upper() if parts else "UNKNOWN"


def _resolve_group(family: str) -> str:
    return family[:4].upper() if family else "UNK"


# ── fuzzy matching ──────────────────────────────────────────────────────────

_known_merchants: dict[str, str] = {}


def _fuzzy_match(normalized: str, threshold: float = 0.85) -> tuple[str, Decimal]:
    """Try to match against known merchants using SequenceMatcher."""
    if not _known_merchants:
        return normalized, Decimal("1.0")

    best_match = normalized
    best_score = 0.0

    for known in _known_merchants:
        ratio = SequenceMatcher(None, normalized, known).ratio()
        if ratio > best_score:
            best_score = ratio
            best_match = known

    if best_score >= threshold:
        return _known_merchants[best_match], Decimal(str(round(best_score, 2)))
    return normalized, Decimal("1.0")


class StatementNormalizer:
    """Normalize parsed rows into canonical transaction payloads."""

    _punct_re = re.compile(r"[^\w\s]+", re.UNICODE)

    @staticmethod
    def normalize_currency(currency: str) -> str:
        mapping = {"RUR": "RUB", "₽": "RUB"}
        normalized = currency.upper().strip()
        return mapping.get(normalized, normalized)

    def normalize_merchant(self, merchant_raw: str) -> NormalizedMerchant:
        compact = re.sub(r"\s+", " ", merchant_raw.strip().lower())
        normalized = self._punct_re.sub("", compact).strip() or "unknown"
        alias_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        # Try fuzzy matching against known merchants
        matched, confidence = _fuzzy_match(normalized.upper())
        canonical = matched if confidence >= Decimal("0.85") else normalized.upper()

        family = _resolve_family(canonical)
        group = _resolve_group(family)

        # Register for future fuzzy matching
        _known_merchants[normalized] = canonical

        return NormalizedMerchant(
            merchant_alias=merchant_raw.strip() or "UNKNOWN",
            normalized_merchant_name=canonical,
            merchant_family=family,
            merchant_group=group,
            confidence_score=confidence,
            alias_hash=alias_hash,
        )

    def normalize_rows(self, rows: list[dict]) -> list[dict]:
        normalized_rows: list[dict] = []
        for row in rows:
            merchant = self.normalize_merchant(row.get("merchant_raw", "UNKNOWN"))
            amount = Decimal(str(row.get("amount_signed_original", 0)))
            currency = self.normalize_currency(str(row.get("currency_original", "RUB")))

            is_credit = amount > 0
            normalized_rows.append(
                {
                    **row,
                    "currency_normalized": currency,
                    "amount_signed_original": amount,
                    "inflow_amount": amount if is_credit else Decimal("0"),
                    "outflow_amount": abs(amount) if amount < 0 else Decimal("0"),
                    "fee_amount": Decimal("0"),
                    "operation_type": "credit" if is_credit else "debit",
                    "is_credit": is_credit,
                    "merchant_raw": merchant.merchant_alias,
                    "merchant_normalized": merchant.normalized_merchant_name,
                    "merchant_group": merchant.merchant_group,
                    "is_refund_candidate": is_credit,
                    "is_duplicate_candidate": False,
                    "is_burst_candidate": False,
                    "explanation_json": {},
                }
            )

        return normalized_rows

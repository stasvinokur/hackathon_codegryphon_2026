from __future__ import annotations

from pathlib import Path

from app.services.parsers.statement_pdf_parser import StatementPdfParser

SAMPLE_TEXT = """\
Номер карты 220024******8339
Период выписки 01.01.2024 - 15.07.2025
Кредитный лимит 1,000,000.00 RUB
Доступный остаток 131,896.88 RUB
Общая сумма задолженности* 876,200.74
Минимальный платеж 20,900.00 RUB
Статус беспроцентного периода Действует
Операции по карте
Проведена Обработана В валюте Поступление Расход Комиссия Задолженность Описание операции
14.07.2025
11:51:54
14.07.2025
19:29:03
-500.00 RUB 0 RUB 500.00 RUB 0.00 RUB 867,198.12 Оплата товаров и услуг. METRO
13.07.2025
05:54:30
14.07.2025
17:10:09
-399.00 RUB 0 RUB 399.00 RUB 0.00 RUB 866,698.12 Оплата товаров и услуг. YANDEX*5815*PLUS
12.02.2024
18:41:20
14.02.2024
04:04:26
3,000.00 RUB 3,000.00 RUB 0 RUB 0.00 RUB 261,236.56 OOO STIMUL
"""


def _write_sample(tmp_path: Path) -> Path:
    p = tmp_path / "sample.pdf"
    p.write_text(SAMPLE_TEXT, encoding="utf-8")
    return p


def test_parse_transactions_count(tmp_path: Path) -> None:
    parser = StatementPdfParser()
    rows = parser.parse_transactions(str(_write_sample(tmp_path)))
    assert len(rows) == 3


def test_parse_transaction_amounts(tmp_path: Path) -> None:
    parser = StatementPdfParser()
    rows = parser.parse_transactions(str(_write_sample(tmp_path)))
    amounts = [float(r["amount_signed_original"]) for r in rows]
    assert -500.0 in amounts
    assert -399.0 in amounts
    assert 3000.0 in amounts


def test_parse_settlement_lag(tmp_path: Path) -> None:
    parser = StatementPdfParser()
    rows = parser.parse_transactions(str(_write_sample(tmp_path)))
    # First tx: 14.07.2025 11:51:54 -> 14.07.2025 19:29:03 = ~7.6 hours
    lag = float(rows[0]["settlement_lag_hours"])
    assert 7.0 < lag < 8.0


def test_parse_merchant_extraction(tmp_path: Path) -> None:
    parser = StatementPdfParser()
    rows = parser.parse_transactions(str(_write_sample(tmp_path)))
    merchants = [r["merchant_raw"] for r in rows]
    assert "METRO" in merchants
    assert any("YANDEX" in m for m in merchants)


def test_parse_credit_detection(tmp_path: Path) -> None:
    parser = StatementPdfParser()
    rows = parser.parse_transactions(str(_write_sample(tmp_path)))
    credit_rows = [r for r in rows if r.get("is_credit")]
    assert len(credit_rows) == 1
    assert float(credit_rows[0]["amount_signed_original"]) == 3000.0


def test_extract_metadata(tmp_path: Path) -> None:
    parser = StatementPdfParser()
    meta = parser.parse_statement_metadata(str(_write_sample(tmp_path)))
    assert meta["bank_name"] == "ВТБ"
    assert meta["masked_card_number"] == "220024******8339"
    assert float(meta["credit_limit"]) == 1_000_000.0
    assert float(meta["minimum_payment"]) == 20_900.0
    assert meta["grace_period_status"] == "Действует"


def test_parse_nonexistent_file() -> None:
    parser = StatementPdfParser()
    assert parser.parse_transactions("/nonexistent/file.pdf") == []
    assert parser.parse_statement_metadata("/nonexistent/file.pdf") == {}

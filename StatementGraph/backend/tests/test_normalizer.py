from __future__ import annotations

from decimal import Decimal

from app.services.normalization.normalizer import StatementNormalizer


def test_normalize_currency_rur_to_rub() -> None:
    normalizer = StatementNormalizer()
    assert normalizer.normalize_currency("RUR") == "RUB"
    assert normalizer.normalize_currency("₽") == "RUB"
    assert normalizer.normalize_currency("USD") == "USD"


def test_normalize_merchant_basic() -> None:
    normalizer = StatementNormalizer()
    result = normalizer.normalize_merchant("YANDEX*5815*PLUS")
    assert result.normalized_merchant_name  # not empty
    assert result.merchant_family == "YANDEX"
    assert result.alias_hash  # SHA256 present
    assert result.confidence_score > Decimal("0")


def test_normalize_merchant_metro() -> None:
    normalizer = StatementNormalizer()
    result = normalizer.normalize_merchant("METRO")
    assert result.merchant_family == "METRO"
    assert result.merchant_group == "METR"


def test_normalize_merchant_hosting() -> None:
    normalizer = StatementNormalizer()
    result = normalizer.normalize_merchant("HOSTINGVDSCOM")
    assert result.merchant_family == "HOSTING"


def test_normalize_rows() -> None:
    normalizer = StatementNormalizer()
    rows = normalizer.normalize_rows([
        {
            "amount_signed_original": Decimal("-500"),
            "currency_original": "RUB",
            "merchant_raw": "METRO",
        },
        {
            "amount_signed_original": Decimal("3000"),
            "currency_original": "RUR",
            "merchant_raw": "OOO STIMUL",
        },
    ])
    assert len(rows) == 2
    assert rows[0]["operation_type"] == "debit"
    assert rows[0]["outflow_amount"] == Decimal("500")
    assert rows[1]["operation_type"] == "credit"
    assert rows[1]["inflow_amount"] == Decimal("3000")
    assert rows[1]["currency_normalized"] == "RUB"


def test_fuzzy_matching_consistency() -> None:
    """Normalizing the same merchant twice should give the same result."""
    normalizer = StatementNormalizer()
    r1 = normalizer.normalize_merchant("new. pik-comfort.ru")
    r2 = normalizer.normalize_merchant("NEW. PIK-COMFORT. RU")
    assert r1.merchant_family == r2.merchant_family == "PIK"

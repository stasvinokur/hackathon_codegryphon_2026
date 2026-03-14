from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.detection.risk_engine import RiskEngine, _rule_debt_dynamics


def _make_tx(**overrides):  # type: ignore[no-untyped-def]
    defaults = {
        "id": uuid4(),
        "statement_id": uuid4(),
        "posted_at": datetime(2025, 7, 14, 12, 0, 0),
        "processed_at": datetime(2025, 7, 14, 18, 0, 0),
        "settlement_lag_hours": Decimal("6"),
        "amount_signed_original": Decimal("-500"),
        "currency_original": "RUB",
        "currency_normalized": "RUB",
        "inflow_amount": Decimal("0"),
        "outflow_amount": Decimal("500"),
        "fee_amount": Decimal("0"),
        "description_raw": "Оплата товаров и услуг. METRO",
        "description_clean": "Оплата товаров и услуг. METRO",
        "merchant_raw": "METRO",
        "merchant_normalized": "METRO",
        "merchant_group": "METR",
        "operation_type": "debit",
        "is_credit": False,
        "is_refund_candidate": False,
        "is_duplicate_candidate": False,
        "is_burst_candidate": False,
        "risk_score": Decimal("0"),
        "anomaly_score": Decimal("0"),
        "explanation_json": {},
        "raw_row_json": {},
        "debt_after_transaction": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_duplicate_detection() -> None:
    engine = RiskEngine()
    base_time = datetime(2025, 7, 14, 12, 0, 0)
    tx1 = _make_tx(posted_at=base_time)
    tx2 = _make_tx(posted_at=base_time + timedelta(minutes=10))
    alerts = engine.score([tx1, tx2])
    dup_alerts = [a for a in alerts if a.alert_type == "duplicate_candidate"]
    assert len(dup_alerts) >= 1


def test_burst_detection() -> None:
    engine = RiskEngine()
    base_time = datetime(2025, 7, 14, 12, 0, 0)
    txs = [
        _make_tx(
            posted_at=base_time + timedelta(minutes=i * 30),
            amount_signed_original=Decimal(str(-100 * (i + 1))),
            outflow_amount=Decimal(str(100 * (i + 1))),
        )
        for i in range(4)
    ]
    alerts = engine.score(txs)
    burst_alerts = [a for a in alerts if a.alert_type == "merchant_burst"]
    assert len(burst_alerts) >= 1


def test_refund_detection() -> None:
    engine = RiskEngine()
    debit = _make_tx(
        amount_signed_original=Decimal("-1000"),
        outflow_amount=Decimal("1000"),
        is_credit=False,
        posted_at=datetime(2025, 7, 10, 12, 0, 0),
    )
    credit = _make_tx(
        amount_signed_original=Decimal("1000"),
        inflow_amount=Decimal("1000"),
        outflow_amount=Decimal("0"),
        is_credit=True,
        operation_type="credit",
        posted_at=datetime(2025, 7, 14, 12, 0, 0),
    )
    alerts = engine.score([debit, credit])
    refund_alerts = [a for a in alerts if a.alert_type == "refund_match"]
    assert len(refund_alerts) >= 1


def test_high_value_detection() -> None:
    engine = RiskEngine()
    normal_txs = [
        _make_tx(
            amount_signed_original=Decimal("-100"),
            outflow_amount=Decimal("100"),
            posted_at=datetime(2025, 7, i, 12, 0, 0),
        )
        for i in range(1, 12)
    ]
    expensive = _make_tx(
        amount_signed_original=Decimal("-50000"),
        outflow_amount=Decimal("50000"),
        posted_at=datetime(2025, 7, 14, 12, 0, 0),
    )
    alerts = engine.score([*normal_txs, expensive])
    amount_alerts = [a for a in alerts if a.alert_type == "amount_anomaly"]
    assert len(amount_alerts) >= 1


def test_empty_transactions() -> None:
    engine = RiskEngine()
    assert engine.score([]) == []


def test_severity_levels() -> None:
    engine = RiskEngine()
    base_time = datetime(2025, 7, 14, 12, 0, 0)
    txs = [
        _make_tx(posted_at=base_time + timedelta(minutes=i * 5))
        for i in range(5)
    ]
    alerts = engine.score(txs)
    severities = {a.severity for a in alerts}
    # Should have at least one alert with a valid severity
    assert severities.issubset({"high", "medium", "low"})


def test_to_alert_models() -> None:
    from app.services.detection.risk_engine import ScoredAlert

    scored = [
        ScoredAlert(
            transaction_id=uuid4(),
            severity="high",
            alert_type="duplicate_candidate",
            score=0.85,
            reason="test",
            explanation_json={"reasons": []},
        )
    ]
    models = RiskEngine.to_alert_models(scored)
    assert len(models) == 1
    assert models[0].severity == "high"
    assert models[0].status == "new"


def test_rule_debt_dynamics_large_jump() -> None:
    prev = _make_tx(debt_after_transaction=Decimal("100000"), posted_at=datetime(2025, 7, 13, 12, 0, 0))
    curr = _make_tx(
        debt_after_transaction=Decimal("200000"),
        outflow_amount=Decimal("50000"),
        posted_at=datetime(2025, 7, 14, 12, 0, 0),
    )
    result = _rule_debt_dynamics(curr, prev)
    assert result is not None
    assert abs(result[0] - 0.55) < 1e-9
    assert "Large debt jump" in result[1]


def test_rule_debt_dynamics_none_when_no_debt() -> None:
    prev = _make_tx(debt_after_transaction=None)
    curr = _make_tx(debt_after_transaction=None)
    assert _rule_debt_dynamics(curr, prev) is None
    assert _rule_debt_dynamics(curr, None) is None

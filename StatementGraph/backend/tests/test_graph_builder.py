from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.graph.graph_builder import build_nx_graph, nx_graph_features


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
        "description_raw": "METRO",
        "description_clean": "METRO",
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
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_build_nx_graph_nodes_and_edges() -> None:
    tx1 = _make_tx()
    tx2 = _make_tx()
    g = build_nx_graph([tx1, tx2])
    # Should have 2 transaction nodes + 1 merchant node + 1 merchant group node
    assert g.number_of_nodes() == 4
    # Each tx -> merchant edge + merchant -> group edge
    assert g.number_of_edges() >= 3


def test_duplicate_edges_created() -> None:
    base = datetime(2025, 7, 14, 12, 0, 0)
    tx1 = _make_tx(posted_at=base)
    tx2 = _make_tx(posted_at=base + timedelta(minutes=10))
    g = build_nx_graph([tx1, tx2])
    dup_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("rel") == "POSSIBLE_DUPLICATE_OF"]
    assert len(dup_edges) == 1


def test_refund_edges_created() -> None:
    debit = _make_tx(
        amount_signed_original=Decimal("-1000"),
        is_credit=False,
        posted_at=datetime(2025, 7, 10, 12, 0, 0),
    )
    credit = _make_tx(
        amount_signed_original=Decimal("1000"),
        is_credit=True,
        posted_at=datetime(2025, 7, 14, 12, 0, 0),
    )
    g = build_nx_graph([debit, credit])
    refund_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("rel") == "POSSIBLE_REFUND_FOR"]
    assert len(refund_edges) == 1


def test_burst_edges_created() -> None:
    base = datetime(2025, 7, 14, 12, 0, 0)
    txs = [_make_tx(posted_at=base + timedelta(hours=i)) for i in range(3)]
    g = build_nx_graph(txs)
    burst_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("rel") == "BURST_WITHIN_WINDOW"]
    assert len(burst_edges) >= 2


def test_nx_graph_features() -> None:
    base = datetime(2025, 7, 14, 12, 0, 0)
    txs = [_make_tx(posted_at=base + timedelta(minutes=i * 10)) for i in range(3)]
    g = build_nx_graph(txs)
    features = nx_graph_features(g)
    assert len(features) == 3
    for feat in features.values():
        assert "degree" in feat
        assert "betweenness" in feat
        assert "duplicate_neighbors" in feat


def test_similar_amount_edges_created() -> None:
    base = datetime(2025, 7, 14, 12, 0, 0)
    tx1 = _make_tx(
        merchant_normalized="SHOP_A",
        merchant_raw="SHOP_A",
        amount_signed_original=Decimal("-1000"),
        outflow_amount=Decimal("1000"),
        posted_at=base,
    )
    tx2 = _make_tx(
        merchant_normalized="SHOP_B",
        merchant_raw="SHOP_B",
        merchant_group="SHOPB",
        amount_signed_original=Decimal("-1000"),
        outflow_amount=Decimal("1000"),
        posted_at=base + timedelta(days=2),
    )
    g = build_nx_graph([tx1, tx2])
    similar_edges = [(u, v) for u, v, d in g.edges(data=True) if d.get("rel") == "SIMILAR_AMOUNT_PATTERN"]
    assert len(similar_edges) == 1

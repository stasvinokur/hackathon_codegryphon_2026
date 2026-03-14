from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import networkx as nx
from neo4j import GraphDatabase
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.alert import Alert
from app.models.statement import Statement
from app.models.transaction import Transaction


@dataclass(slots=True)
class GraphPayload:
    nodes: list[dict]
    edges: list[dict]


_SEVERITY_RU = {"high": "высокий", "medium": "средний", "low": "низкий"}

# ── NetworkX feature helpers ────────────────────────────────────────────────


def _add_merchant_group_nodes(
    g: nx.MultiDiGraph, merchant_name: str, txs: list[Transaction],
) -> None:
    """Add MerchantGroup nodes and IN_GROUP edges for a merchant's transactions."""
    groups_linked: set[str] = set()
    for tx in txs:
        grp = tx.merchant_group
        if not grp:
            continue
        if grp not in groups_linked:
            groups_linked.add(grp)
            if f"group-{grp}" not in g:
                g.add_node(f"group-{grp}", kind="MerchantGroup", name=grp)
            g.add_edge(f"merchant-{merchant_name}", f"group-{grp}", rel="IN_GROUP")


def build_nx_graph(
    transactions: list[Transaction], *, card_number: str | None = None,
) -> nx.MultiDiGraph:
    """Build a NetworkX graph with suspicious links between transactions."""
    g = nx.MultiDiGraph()

    by_merchant: defaultdict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        g.add_node(
            str(tx.id),
            kind="Transaction",
            amount=float(tx.amount_signed_original),
            merchant=tx.merchant_normalized or tx.merchant_raw,
            risk=float(tx.risk_score or 0),
            posted_at=str(tx.posted_at) if tx.posted_at else "",
        )
        by_merchant[tx.merchant_normalized or "UNKNOWN"].append(tx)

    for m, txs in by_merchant.items():
        g.add_node(f"merchant-{m}", kind="Merchant", name=m, tx_count=len(txs))
        for tx in txs:
            g.add_edge(str(tx.id), f"merchant-{m}", rel="AT_ALIAS")
        _add_merchant_group_nodes(g, m, txs)

    if card_number:
        g.add_node(f"card-{card_number}", kind="Card", number=card_number)

    for m, txs in by_merchant.items():
        _add_duplicate_edges(g, txs)
        _add_refund_edges(g, txs)
        _add_burst_edges(g, txs)

    _add_similar_amount_edges(g, transactions)

    return g


def _add_duplicate_edges(g: nx.MultiDiGraph, txs: list[Transaction]) -> None:
    for i, a in enumerate(txs):
        for b in txs[i + 1 :]:
            if a.amount_signed_original != b.amount_signed_original:
                continue
            if not a.posted_at or not b.posted_at:
                continue
            if abs((a.posted_at - b.posted_at).total_seconds()) <= 1800:
                g.add_edge(str(a.id), str(b.id), rel="POSSIBLE_DUPLICATE_OF")


def _add_refund_edges(g: nx.MultiDiGraph, txs: list[Transaction]) -> None:
    debits = [t for t in txs if not t.is_credit and t.posted_at]
    credits = [t for t in txs if t.is_credit and t.posted_at]
    for cr in credits:
        amt = abs(cr.amount_signed_original)
        tol = amt * Decimal("0.1")
        for db in debits:
            if db.posted_at >= cr.posted_at:  # type: ignore[operator]
                continue
            if abs(abs(db.amount_signed_original) - amt) <= tol:
                g.add_edge(str(cr.id), str(db.id), rel="POSSIBLE_REFUND_FOR")
                break


def _is_similar_amount_pair(a: Transaction, b: Transaction) -> bool:
    """Check if two transactions have similar amounts at different merchants within 7 days."""
    if a.merchant_normalized == b.merchant_normalized:
        return False
    gap_days = abs((b.posted_at - a.posted_at).total_seconds()) / 86400  # type: ignore[operator]
    if gap_days > 7:
        return False
    amt_a = abs(float(a.amount_signed_original))
    amt_b = abs(float(b.amount_signed_original))
    return amt_a > 0 and abs(amt_a - amt_b) / amt_a <= 0.05


def _add_similar_amount_edges(g: nx.MultiDiGraph, transactions: list[Transaction]) -> None:
    """Link debit transactions at different merchants with similar amounts within 7 days."""
    debits = [t for t in transactions if not t.is_credit and t.posted_at and t.outflow_amount]
    debits.sort(key=lambda t: t.posted_at)  # type: ignore[arg-type,return-value]
    added = 0
    for i, a in enumerate(debits):
        if added >= 50:
            break
        for b in debits[i + 1:]:
            if added >= 50 or abs((b.posted_at - a.posted_at).total_seconds()) / 86400 > 7:  # type: ignore[operator]
                break
            if _is_similar_amount_pair(a, b):
                g.add_edge(str(a.id), str(b.id), rel="SIMILAR_AMOUNT_PATTERN")
                added += 1


def _add_burst_edges(g: nx.MultiDiGraph, txs: list[Transaction]) -> None:
    sorted_txs = sorted(txs, key=lambda t: t.posted_at or t.processed_at or t.posted_at)  # noqa: S5806
    for i, a in enumerate(sorted_txs):
        if not a.posted_at:
            continue
        win_end = a.posted_at + timedelta(hours=3)
        for b in sorted_txs[i + 1 :]:
            if not b.posted_at:
                continue
            if b.posted_at > win_end:
                break
            g.add_edge(str(a.id), str(b.id), rel="BURST_WITHIN_WINDOW")


def nx_graph_features(g: nx.MultiDiGraph) -> dict[str, dict]:
    """Compute per-node graph features using NetworkX."""
    features: dict[str, dict] = {}
    undirected = g.to_undirected()
    degree = dict(undirected.degree())
    try:
        betweenness = nx.betweenness_centrality(undirected)
    except Exception:
        betweenness = dict.fromkeys(g.nodes, 0.0)

    for node in g.nodes:
        data = g.nodes[node]
        if data.get("kind") != "Transaction":
            continue
        dup_count = sum(1 for _, _, _, d in g.edges(node, data=True, keys=True) if d.get("rel") == "POSSIBLE_DUPLICATE_OF")
        refund_count = sum(1 for _, _, _, d in g.edges(node, data=True, keys=True) if d.get("rel") == "POSSIBLE_REFUND_FOR")
        burst_count = sum(1 for _, _, _, d in g.edges(node, data=True, keys=True) if d.get("rel") == "BURST_WITHIN_WINDOW")
        features[node] = {
            "degree": degree.get(node, 0),
            "betweenness": betweenness.get(node, 0.0),
            "duplicate_neighbors": dup_count,
            "refund_neighbors": refund_count,
            "burst_neighbors": burst_count,
        }
    return features


# ── service ─────────────────────────────────────────────────────────────────


class GraphBuilderService:
    """Build and query investigation graphs from transactional evidence."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._settings = get_settings()

    def _driver(self):
        return GraphDatabase.driver(
            self._settings.neo4j_uri,
            auth=(self._settings.neo4j_user, self._settings.neo4j_password),
        )

    # ── Neo4j sync ──────────────────────────────────────────────────────────

    def sync_statement_graph(self, statement_id: UUID) -> None:
        statement = self._session.get(Statement, statement_id)
        transactions = (
            self._session.query(Transaction).filter(Transaction.statement_id == statement_id).all()
        )
        alerts = (
            self._session.query(Alert)
            .join(Transaction, Alert.transaction_id == Transaction.id)
            .filter(Transaction.statement_id == statement_id)
            .all()
        )

        card_number = statement.masked_card_number if statement else None
        nxg = build_nx_graph(transactions, card_number=card_number)

        try:
            with self._driver() as driver, driver.session() as neo:
                neo.run("MATCH (s:Statement {id: $id}) DETACH DELETE s", id=str(statement_id))
                neo.run("CREATE (:Statement {id: $id})", id=str(statement_id))

                self._sync_transactions(neo, transactions, str(statement_id))
                self._sync_alerts(neo, alerts)
                self._sync_suspicious_links(neo, nxg)
                self._sync_graph_nodes(neo, nxg, str(statement_id))
        except Exception:
            return

    @staticmethod
    def _sync_transactions(neo, transactions: list[Transaction], statement_id: str) -> None:
        for tx in transactions:
            neo.run(
                """
                MERGE (t:Transaction {id: $tx_id})
                SET t.amount = $amount, t.merchant = $merchant,
                    t.posted_at = $posted_at, t.risk_score = $risk_score
                WITH t
                MATCH (s:Statement {id: $statement_id})
                MERGE (s)-[:CONTAINS]->(t)
                MERGE (m:Merchant {name: $merchant})
                MERGE (t)-[:AT_ALIAS]->(m)
                """,
                tx_id=str(tx.id),
                amount=float(tx.amount_signed_original),
                merchant=tx.merchant_normalized or tx.merchant_raw,
                posted_at=tx.posted_at.isoformat() if tx.posted_at else None,
                risk_score=float(tx.risk_score or 0),
                statement_id=statement_id,
            )

    @staticmethod
    def _sync_alerts(neo, alerts: list[Alert]) -> None:
        for alert in alerts:
            neo.run(
                """
                MERGE (a:Alert {id: $alert_id})
                SET a.type = $type, a.severity = $severity,
                    a.score = $score, a.reason = $reason
                WITH a
                MATCH (t:Transaction {id: $tx_id})
                MERGE (a)-[:FLAGS]->(t)
                """,
                alert_id=str(alert.id),
                type=alert.alert_type,
                severity=alert.severity,
                score=float(alert.score),
                reason=alert.reason,
                tx_id=str(alert.transaction_id),
            )

    @staticmethod
    def _sync_graph_nodes(neo, nxg: nx.MultiDiGraph, statement_id: str) -> None:
        """Sync MerchantGroup and Card nodes from NX graph to Neo4j."""
        for node, data in nxg.nodes(data=True):
            kind = data.get("kind")
            if kind == "MerchantGroup":
                neo.run(
                    "MERGE (mg:MerchantGroup {name: $name})",
                    name=data.get("name", node),
                )
            elif kind == "Card":
                neo.run(
                    """
                    MERGE (c:Card {number: $number})
                    WITH c
                    MATCH (s:Statement {id: $sid})
                    MERGE (s)-[:HAS_CARD]->(c)
                    """,
                    number=data.get("number", node),
                    sid=statement_id,
                )
        # IN_GROUP edges
        for u, v, data in nxg.edges(data=True):
            if data.get("rel") == "IN_GROUP":
                neo.run(
                    """
                    MATCH (m:Merchant {name: $merchant})
                    MATCH (mg:MerchantGroup {name: $group})
                    MERGE (m)-[:IN_GROUP]->(mg)
                    """,
                    merchant=nxg.nodes[u].get("name", u),
                    group=nxg.nodes[v].get("name", v),
                )

    @staticmethod
    def _sync_suspicious_links(neo, nxg: nx.MultiDiGraph) -> None:
        rel_types = {"POSSIBLE_DUPLICATE_OF", "POSSIBLE_REFUND_FOR", "BURST_WITHIN_WINDOW", "SIMILAR_AMOUNT_PATTERN"}
        for u, v, data in nxg.edges(data=True):
            rel = data.get("rel", "")
            if rel not in rel_types:
                continue
            neo.run(
                f"""
                MATCH (a:Transaction {{id: $u}})
                MATCH (b:Transaction {{id: $v}})
                MERGE (a)-[:{rel}]->(b)
                """,
                u=u,
                v=v,
            )

    # ── in-memory graph queries ─────────────────────────────────────────────

    def graph_for_alert(self, alert_id: UUID) -> GraphPayload:
        alert = self._session.get(Alert, alert_id)
        if alert is None:
            return GraphPayload(nodes=[], edges=[])

        tx = self._session.get(Transaction, alert.transaction_id)
        if tx is None:
            return GraphPayload(nodes=[], edges=[])

        peers = (
            self._session.query(Transaction)
            .filter(Transaction.merchant_normalized == tx.merchant_normalized)
            .limit(15)
            .all()
        )

        # Build local graph for suspicious links
        nxg = build_nx_graph([tx, *peers])
        return self._nxg_to_payload(nxg, alert=alert)

    def graph_for_merchant(self, merchant_name: str) -> GraphPayload:
        txs = (
            self._session.query(Transaction)
            .filter(Transaction.merchant_normalized == merchant_name)
            .limit(50)
            .all()
        )
        if not txs:
            return GraphPayload(nodes=[], edges=[])
        nxg = build_nx_graph(txs)
        return self._nxg_to_payload(nxg)

    @staticmethod
    def _nxg_to_payload(nxg: nx.MultiDiGraph, alert: Alert | None = None) -> GraphPayload:
        """Convert a NetworkX graph to a frontend-consumable payload."""
        nodes: list[dict] = []
        edges: list[dict] = []

        if alert:
            nodes.append({
                "data": {
                    "id": f"alert-{alert.id}",
                    "label": f"Алерт ({_SEVERITY_RU.get(alert.severity, alert.severity)})",
                    "nodeType": "Alert",
                    "severity": alert.severity,
                }
            })
            edges.append({
                "data": {
                    "id": f"e-alert-{alert.id}",
                    "source": f"alert-{alert.id}",
                    "target": str(alert.transaction_id),
                    "type": "FLAGS",
                }
            })

        for node, data in nxg.nodes(data=True):
            kind = data.get("kind", "Unknown")
            if kind == "Merchant":
                label = data.get("name", node)
            elif kind == "MerchantGroup":
                label = data.get("name", node)
            elif kind == "Card":
                label = data.get("number", node)
            else:
                amt = data.get("amount", "?")
                posted = str(data.get("posted_at", ""))[:10]
                label = f"{amt} ({posted})" if posted else str(amt)
            nodes.append({
                "data": {
                    "id": node,
                    "label": label,
                    "nodeType": kind,
                    "risk": data.get("risk", 0),
                    **{k: v for k, v in data.items() if k not in ("kind",)},
                }
            })

        for u, v, data in nxg.edges(data=True):
            rel = data.get("rel", "RELATED")
            edges.append({
                "data": {
                    "id": f"e-{u}-{v}-{rel}",
                    "source": u,
                    "target": v,
                    "type": rel,
                }
            })

        return GraphPayload(nodes=nodes, edges=edges)

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from statistics import median, stdev
from uuid import UUID

import numpy as np
from sklearn.ensemble import IsolationForest

from app.models.alert import Alert
from app.models.transaction import Transaction


@dataclass(slots=True)
class ScoredAlert:
    """Intermediate scored alert payload produced by the risk engine."""

    transaction_id: UUID
    severity: str
    alert_type: str
    score: float
    reason: str
    explanation_json: dict


# ── individual rules ────────────────────────────────────────────────────────


def _rule_duplicate(tx: Transaction, peers: list[Transaction]) -> tuple[float, str] | None:
    for peer in peers:
        if peer.id == tx.id or peer.merchant_normalized != tx.merchant_normalized:
            continue
        if peer.amount_signed_original != tx.amount_signed_original:
            continue
        if not peer.posted_at or not tx.posted_at:
            continue
        gap = abs((peer.posted_at - tx.posted_at).total_seconds())
        if gap <= 30 * 60:
            return 0.8, "Возможный дубликат списания (менее 30 мин)"
        if gap <= 86400 and abs(float(tx.amount_signed_original)) < 200:
            return 0.6, "Повторное мелкое списание за 24 часа"
    return None


def _rule_burst(tx: Transaction, count_3h: int, same_day: int) -> tuple[float, str] | None:
    if tx.is_credit:
        return None
    if count_3h >= 3:
        return 0.7, f"Всплеск активности: {count_3h} списаний за 3 часа"
    if same_day >= 4:
        return 0.65, f"Множественные списания за день: {same_day} шт."
    return None


def _rule_refund(tx: Transaction, all_txs: list[Transaction]) -> tuple[float, str] | None:
    """Match incoming credit to a prior debit by amount and merchant."""
    if not tx.is_credit or not tx.posted_at:
        return None
    amt = abs(tx.amount_signed_original)
    tolerance = amt * Decimal("0.1")
    for peer in all_txs:
        if peer.is_credit or peer.id == tx.id or not peer.posted_at:
            continue
        if peer.posted_at >= tx.posted_at:
            continue
        if peer.merchant_normalized != tx.merchant_normalized:
            continue
        if abs(abs(peer.amount_signed_original) - amt) <= tolerance:
            return 0.7, f"Возврат: зачисление соответствует списанию у {peer.merchant_normalized}"
    return None


def _rule_high_value(
    tx: Transaction, merchant_median: Decimal, global_median: Decimal, merchant_tx_count: int
) -> tuple[float, str] | None:
    if not tx.outflow_amount:
        return None
    if merchant_tx_count <= 1 and tx.outflow_amount > global_median * Decimal("3"):
        return 0.65, "Аномально крупная сумма у нового мерчанта"
    if merchant_median > 0 and tx.outflow_amount > merchant_median * Decimal("3"):
        return 0.6, "Сумма значительно выше базового уровня мерчанта"
    if global_median > 0 and tx.outflow_amount > global_median * Decimal("5"):
        return 0.55, "Сумма значительно выше общей медианы транзакций"
    return None


def _rule_settlement(tx: Transaction, merchant_median_lag: float) -> tuple[float, str] | None:
    lag = float(tx.settlement_lag_hours or 0)
    if lag <= 0:
        return None
    if merchant_median_lag > 0 and lag > merchant_median_lag * 3:
        return 0.5, f"Задержка расчёта {lag:.1f}ч значительно выше средней {merchant_median_lag:.1f}ч"
    if lag > 72:
        return 0.45, f"Длительная задержка расчёта: {lag:.1f}ч"
    return None


def _rule_merchant_hygiene(
    tx: Transaction, alias_count: int, merchant_tx_count: int
) -> tuple[float, str] | None:
    if alias_count >= 5:
        return 0.5, f"У мерчанта {alias_count} вариантов названия"
    if merchant_tx_count == 1 and tx.outflow_amount and float(tx.outflow_amount) > 5000:
        return 0.45, "Неизвестный мерчант с крупным списанием"
    return None


def _rule_debt_dynamics(tx: Transaction, prev_tx: Transaction | None) -> tuple[float, str] | None:
    """Detect large debt jumps or debt changes inconsistent with transaction amount."""
    if prev_tx is None or tx.debt_after_transaction is None or prev_tx.debt_after_transaction is None:
        return None
    prev_debt = float(prev_tx.debt_after_transaction)
    curr_debt = float(tx.debt_after_transaction)
    if prev_debt <= 0:
        return None
    debt_delta = curr_debt - prev_debt
    if debt_delta <= 0:
        return None
    # Large debt jump: >50% increase
    if debt_delta / prev_debt > 0.5:
        return 0.55, f"Резкий рост долга: {prev_debt:.0f} → {curr_debt:.0f} (+{debt_delta / prev_debt * 100:.0f}%)"
    # Inconsistent magnitude: outflow < 5% of debt change
    outflow = float(tx.outflow_amount or 0)
    if outflow > 0 and outflow < debt_delta * 0.05:
        return 0.5, "Изменение долга не соответствует сумме транзакции"
    return None


def _rule_recurring_interval(tx: Transaction, peers: list[Transaction]) -> tuple[float, str] | None:
    """Detect broken recurring payment patterns.

    Groups by merchant + similar amount (±10%), computes intervals
    between consecutive transactions, and flags if the current tx
    deviates significantly from the established rhythm.
    """
    if tx.is_credit or not tx.posted_at or len(peers) < 3:
        return None
    amt = abs(float(tx.amount_signed_original))
    tolerance = amt * 0.1

    similar = sorted(
        (p for p in peers if p.posted_at and not p.is_credit and abs(abs(float(p.amount_signed_original)) - amt) <= tolerance),
        key=lambda p: p.posted_at,  # type: ignore[arg-type,return-value]
    )
    if len(similar) < 3:
        return None

    intervals = [
        (similar[i + 1].posted_at - similar[i].posted_at).total_seconds() / 3600  # type: ignore[operator]
        for i in range(len(similar) - 1)
    ]
    mean_interval = sum(intervals) / len(intervals)
    if mean_interval < 12:
        return None
    if len(intervals) < 2:
        return None
    sd = stdev(intervals)
    if sd >= mean_interval * 0.55:
        return None  # not a regular pattern

    # Find this tx in the sorted list and check its interval
    for i, p in enumerate(similar):
        if p.id != tx.id:
            continue
        if i == 0:
            gap = intervals[0]
        else:
            gap = (tx.posted_at - similar[i - 1].posted_at).total_seconds() / 3600  # type: ignore[operator]
        if abs(gap - mean_interval) > mean_interval * 2:
            return 0.5, f"Аномалия регулярности: ожидалось ~{mean_interval:.0f}ч, получено {gap:.0f}ч"
        break
    return None


# ── precompute context ──────────────────────────────────────────────────────


def _precompute(transactions: list[Transaction]) -> dict:
    by_merchant: defaultdict[str, list[Transaction]] = defaultdict(list)
    merchant_raw_aliases: defaultdict[str, set[str]] = defaultdict(set)
    merchant_lags: defaultdict[str, list[float]] = defaultdict(list)
    all_outflows: list[float] = []

    for tx in transactions:
        m = tx.merchant_normalized or "UNKNOWN"
        by_merchant[m].append(tx)
        merchant_raw_aliases[m].add(tx.merchant_raw)
        if tx.settlement_lag_hours and float(tx.settlement_lag_hours) > 0:
            merchant_lags[m].append(float(tx.settlement_lag_hours))
        if tx.outflow_amount:
            all_outflows.append(float(abs(tx.outflow_amount)))

    global_median = Decimal(str(median(all_outflows))) if all_outflows else Decimal("0")

    # Build previous-transaction map (by posted_at order)
    sorted_txs = sorted((t for t in transactions if t.posted_at), key=lambda t: t.posted_at)  # type: ignore[arg-type,return-value]
    prev_tx_map: dict[UUID, Transaction] = {}
    for i in range(1, len(sorted_txs)):
        prev_tx_map[sorted_txs[i].id] = sorted_txs[i - 1]

    return {
        "by_merchant": dict(by_merchant),
        "merchant_raw_aliases": merchant_raw_aliases,
        "merchant_lags": merchant_lags,
        "global_median": global_median,
        "prev_tx_map": prev_tx_map,
    }


# ── engine ──────────────────────────────────────────────────────────────────


class RiskEngine:
    """Combine explainable rules with unsupervised anomaly scoring."""

    # ── feature engineering ──────────────────────────────────────────────────

    def _build_anomaly_scores(self, transactions: list[Transaction]) -> dict[UUID, float]:
        scores: dict[UUID, float] = {tx.id: 0.0 for tx in transactions}
        if len(transactions) < 10:
            return scores

        merchant_counts: Counter[str] = Counter()
        merchant_amounts: defaultdict[str, list[float]] = defaultdict(list)
        for tx in transactions:
            m = tx.merchant_normalized or "UNKNOWN"
            merchant_counts[m] += 1
            merchant_amounts[m].append(float(abs(tx.amount_signed_original)))

        all_amounts = [float(abs(tx.amount_signed_original)) for tx in transactions]
        global_mean = float(np.mean(all_amounts))
        global_std = max(float(np.std(all_amounts)), 1e-9)

        features = np.array([self._tx_features(tx, merchant_counts, merchant_amounts, global_mean, global_std, transactions, all_amounts) for tx in transactions])
        model = IsolationForest(random_state=42, contamination=0.15)
        model.fit(features)
        score_raw = -model.score_samples(features)

        min_s, max_s = float(np.min(score_raw)), float(np.max(score_raw))
        span = max(max_s - min_s, 1e-9)
        for tx, raw in zip(transactions, score_raw, strict=False):
            scores[tx.id] = (float(raw) - min_s) / span
        return scores

    @staticmethod
    def _tx_features(
        tx: Transaction,
        merchant_counts: Counter[str],
        merchant_amounts: dict[str, list[float]],
        global_mean: float,
        global_std: float,
        transactions: list[Transaction],
        all_amounts: list[float],
    ) -> list[float]:
        m = tx.merchant_normalized or "UNKNOWN"
        m_amounts = merchant_amounts.get(m, [])
        m_mean = float(np.mean(m_amounts)) if len(m_amounts) >= 2 else 0.0
        m_std = max(float(np.std(m_amounts)), 1e-9) if len(m_amounts) >= 2 else 1.0
        m_zscore = (float(abs(tx.amount_signed_original)) - m_mean) / m_std if len(m_amounts) >= 2 else 0.0

        dup_count = sum(
            1
            for p in transactions
            if p.id != tx.id
            and p.merchant_normalized == tx.merchant_normalized
            and p.amount_signed_original == tx.amount_signed_original
        )
        med_all = float(np.median(all_amounts)) if all_amounts else 0.0

        return [
            float(tx.outflow_amount or 0),
            float(tx.inflow_amount or 0),
            float(tx.settlement_lag_hours or 0),
            tx.posted_at.hour if tx.posted_at else 0,
            1.0 if tx.posted_at and tx.posted_at.weekday() >= 5 else 0.0,
            float(merchant_counts.get(m, 0)),
            (float(abs(tx.amount_signed_original)) - global_mean) / global_std,
            m_zscore,
            float(dup_count),
            float(tx.outflow_amount or 0) - med_all,
        ]

    # ── rule evaluation ─────────────────────────────────────────────────────

    @staticmethod
    def _evaluate_rules(
        tx: Transaction,
        peers: list[Transaction],
        all_txs: list[Transaction],
        ctx: dict,
    ) -> list[tuple[str, float, str]]:
        reasons: list[tuple[str, float, str]] = []
        m = tx.merchant_normalized or "UNKNOWN"

        dup = _rule_duplicate(tx, peers)
        if dup:
            reasons.append(("duplicate_candidate", dup[0], dup[1]))

        if tx.posted_at:
            win = tx.posted_at - timedelta(hours=3)
            c3h = sum(1 for p in peers if p.posted_at and win <= p.posted_at <= tx.posted_at)
            sd = sum(1 for p in peers if p.posted_at and p.posted_at.date() == tx.posted_at.date())
            burst = _rule_burst(tx, c3h, sd)
            if burst:
                reasons.append(("merchant_burst", burst[0], burst[1]))

        refund = _rule_refund(tx, all_txs)
        if refund:
            reasons.append(("refund_match", refund[0], refund[1]))

        outflows = [float(abs(p.outflow_amount)) for p in peers if p.outflow_amount]
        merchant_med = Decimal(str(median(outflows))) if outflows else Decimal("0")
        hv = _rule_high_value(tx, merchant_med, ctx["global_median"], len(peers))
        if hv:
            reasons.append(("amount_anomaly", hv[0], hv[1]))

        lags = ctx["merchant_lags"].get(m, [])
        med_lag = median(lags) if lags else 0.0
        stl = _rule_settlement(tx, med_lag)
        if stl:
            reasons.append(("settlement_anomaly", stl[0], stl[1]))

        alias_count = len(ctx["merchant_raw_aliases"].get(m, set()))
        hyg = _rule_merchant_hygiene(tx, alias_count, len(peers))
        if hyg:
            reasons.append(("merchant_hygiene", hyg[0], hyg[1]))

        prev_tx = ctx.get("prev_tx_map", {}).get(tx.id)
        debt = _rule_debt_dynamics(tx, prev_tx)
        if debt:
            reasons.append(("debt_dynamics", debt[0], debt[1]))

        rec = _rule_recurring_interval(tx, peers)
        if rec:
            reasons.append(("recurring_interval_anomaly", rec[0], rec[1]))

        return reasons

    # ── scoring helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _update_transaction(
        tx: Transaction,
        reasons: list[tuple[str, float, str]],
        anomaly: float,
        final_score: float,
    ) -> None:
        tx.anomaly_score = Decimal(str(round(anomaly, 3)))
        tx.risk_score = Decimal(str(round(final_score, 3)))
        tx.is_duplicate_candidate = any(r[0] == "duplicate_candidate" for r in reasons)
        tx.is_burst_candidate = any(r[0] == "merchant_burst" for r in reasons)
        tx.is_refund_candidate = any(r[0] == "refund_match" for r in reasons) or tx.is_credit
        tx.explanation_json = {
            "reasons": [{"type": r[0], "score": r[1], "message": r[2]} for r in reasons],
            "anomaly_score": round(anomaly, 3),
        }

    @staticmethod
    def _create_alert(
        tx: Transaction, reasons: list[tuple[str, float, str]], final_score: float
    ) -> ScoredAlert:
        if final_score >= 0.8:
            severity = "high"
        elif final_score >= 0.55:
            severity = "medium"
        else:
            severity = "low"
        reason_text = "; ".join(r[2] for r in reasons) or "Anomalous pattern"
        # Prefer the most specific rule as alert_type (amount_anomaly is least specific)
        _specificity = {
            "recurring_interval_anomaly": 0, "debt_dynamics": 1, "merchant_hygiene": 2,
            "settlement_anomaly": 3, "refund_match": 4, "merchant_burst": 5,
            "duplicate_candidate": 6, "amount_anomaly": 7,
        }
        alert_type = min(reasons, key=lambda r: _specificity.get(r[0], 99))[0] if reasons else "anomaly"
        return ScoredAlert(
            transaction_id=tx.id,
            severity=severity,
            alert_type=alert_type,
            score=round(final_score, 3),
            reason=reason_text,
            explanation_json=tx.explanation_json,
        )

    # ── main entry point ────────────────────────────────────────────────────

    def score(self, transactions: list[Transaction]) -> list[ScoredAlert]:
        """Mutate transactions with scores and return generated alerts."""
        if not transactions:
            return []

        ctx = _precompute(transactions)
        by_merchant = ctx["by_merchant"]
        anomaly_scores = self._build_anomaly_scores(transactions)
        alerts: list[ScoredAlert] = []

        for tx in transactions:
            peers = by_merchant.get(tx.merchant_normalized or "UNKNOWN", [])
            reasons = self._evaluate_rules(tx, peers, transactions, ctx)

            anomaly = anomaly_scores.get(tx.id, 0.0)
            rule_score = max([r[1] for r in reasons], default=0.0)
            final_score = min(1.0, rule_score * 0.7 + anomaly * 0.3)

            self._update_transaction(tx, reasons, anomaly, final_score)

            if final_score >= 0.4:
                alerts.append(self._create_alert(tx, reasons, final_score))

        return alerts

    @staticmethod
    def to_alert_models(alerts: list[ScoredAlert]) -> list[Alert]:
        """Convert scored payloads into ORM alert instances."""
        return [
            Alert(
                transaction_id=a.transaction_id,
                severity=a.severity,
                alert_type=a.alert_type,
                status="new",
                score=a.score,
                reason=a.reason,
                explanation_json=a.explanation_json,
            )
            for a in alerts
        ]

from __future__ import annotations

import os
from collections import Counter

from ollama import Client

from app.models.alert import Alert
from app.schemas.statement import StatementSummaryResponse

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL_NAME = os.getenv("LLM_MODEL", "deepseek-v3.1:671b-cloud")

SYSTEM_PROMPT = (
    "Ты — опытный финансовый аналитик в банке. "
    "Проанализируй данные банковской выписки и дай краткое заключение на русском языке. "
    "Укажи: основные риски, подозрительные паттерны, рекомендации по дальнейшим действиям. "
    "Будь конкретен, ссылайся на цифры из данных. Ответ — 5-10 предложений."
)

ALERT_TYPE_LABELS: dict[str, str] = {
    "amount_anomaly": "Аномалия суммы",
    "duplicate_candidate": "Дубликат",
    "merchant_burst": "Всплеск мерчанта",
    "refund_match": "Возврат",
    "settlement_anomaly": "Задержка расчёта",
    "merchant_hygiene": "Гигиена мерчанта",
    "debt_dynamics": "Динамика долга",
    "recurring_interval_anomaly": "Аномалия регулярности",
}


def _build_user_prompt(summary: StatementSummaryResponse, alerts: list[Alert]) -> str:
    type_counts = Counter(a.alert_type for a in alerts)
    severity_counts = Counter(a.severity for a in alerts)

    alert_breakdown = "\n".join(
        f"  - {ALERT_TYPE_LABELS.get(t, t)}: {c} шт."
        for t, c in type_counts.most_common()
    )
    severity_breakdown = ", ".join(
        f"{s}: {c}" for s, c in severity_counts.most_common()
    )
    merchants = "\n".join(
        f"  - {m['merchant']}: {m['count']} алертов"
        for m in summary.top_risky_merchants[:5]
    )

    alert_reasons = "\n".join(
        f"  - [{ALERT_TYPE_LABELS.get(a.alert_type, a.alert_type)}] {a.reason} (скоринг: {a.score:.2f})"
        for a in sorted(alerts, key=lambda x: x.score, reverse=True)[:10]
    )

    return f"""Данные банковской выписки:

Всего операций: {summary.total_operations}
Входящие (зачисления): {summary.total_inflow}
Исходящие (списания): {summary.total_outflow}
Подозрительных алертов: {summary.suspicious_alerts}
Возвратов обнаружено: {summary.refunds_detected}
Дубликатов обнаружено: {summary.duplicates_detected}

Распределение алертов по типам:
{alert_breakdown}

Распределение по критичности: {severity_breakdown}

Топ рискованных мерчантов:
{merchants}

Топ-10 алертов по скорингу:
{alert_reasons}

Дай аналитическое заключение."""


def generate_statement_analysis(
    summary: StatementSummaryResponse, alerts: list[Alert]
) -> str:
    client = Client(host=OLLAMA_HOST)
    user_prompt = _build_user_prompt(summary, alerts)

    response = client.chat(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.message.content  # type: ignore[return-value]

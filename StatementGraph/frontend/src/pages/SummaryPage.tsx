import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { getAiAnalysis, getStatementSummary } from "../api/client";
import { StatCard } from "../components/StatCard";
import { LAST_STATEMENT_STORAGE_KEY } from "../constants";

function renderSimpleMarkdown(text: string): string {
  return text
    .replaceAll(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replaceAll(/^(\d+)\.\s+/gm, "<br/>$1. ");
}

function formatMoney(value: string): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? `${amount.toFixed(2)} ₽` : value;
}

export function SummaryPage(): JSX.Element {
  const navigate = useNavigate();
  const [statementId, setStatementId] = useState<string>(() => {
    return localStorage.getItem(LAST_STATEMENT_STORAGE_KEY) ?? "";
  });
  const [copied, setCopied] = useState(false);

  const summaryQuery = useQuery({
    enabled: Boolean(statementId),
    queryKey: ["statement-summary", statementId],
    queryFn: () => getStatementSummary(statementId),
  });

  const aiMutation = useMutation({
    mutationFn: () => getAiAnalysis(statementId),
  });

  const merchants = useMemo(() => {
    return summaryQuery.data?.top_risky_merchants ?? [];
  }, [summaryQuery.data?.top_risky_merchants]);

  function handleExportCsv() {
    if (!summaryQuery.data) return;
    const lines: string[] = ["Тип;Мерчант;Сумма;Дата1;Дата2"];
    for (const r of summaryQuery.data.refund_details ?? []) {
      lines.push(`Возврат;${r.merchant};${r.amount};${r.credit_date};${r.debit_date}`);
    }
    for (const d of summaryQuery.data.duplicate_details ?? []) {
      lines.push(`Дубликат;${d.merchant};${d.amount};${d.time_gap_minutes} мин;`);
    }
    const blob = new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "summary_export.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="page">
      <h2>Сводка по выписке</h2>
      <p className="page-subtitle">Итоги, подозрительная активность и топ рискованных мерчантов.</p>

      <div className="card" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <label className="input-label" htmlFor="summary-statement-id" style={{ margin: 0, whiteSpace: "nowrap" }}>
          ID выписки
        </label>
        {statementId ? (
          <span
            onClick={() => {
              void navigator.clipboard.writeText(statementId);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            style={{ cursor: "pointer", color: copied ? "#4ade80" : "#60a5fa", fontSize: "0.9rem" }}
            title="Нажмите для копирования полного ID"
          >
            {copied ? "Скопировано!" : `${statementId.slice(0, 8)}...`}
          </span>
        ) : (
          <input
            id="summary-statement-id"
            onChange={(event) => setStatementId(event.target.value.trim())}
            placeholder="Вставьте UUID выписки"
            type="text"
            value={statementId}
            style={{ flex: 1 }}
          />
        )}
      </div>

      {summaryQuery.isLoading ? <p>Загрузка сводки...</p> : null}
      {summaryQuery.isError ? <p className="text-danger">Не удалось загрузить сводку для этой выписки.</p> : null}

      {summaryQuery.data ? (
        <>
          <div className="stats-grid">
            <StatCard label="Всего операций" value={summaryQuery.data.total_operations} />
            <StatCard label="Подозрительные алерты" tone="danger" value={summaryQuery.data.suspicious_alerts} onClick={() => navigate('/alerts')} />
            <StatCard label="Входящие" tone="success" value={formatMoney(summaryQuery.data.total_inflow)} />
            <StatCard label="Исходящие" value={formatMoney(summaryQuery.data.total_outflow)} />
            <StatCard label="Кандидаты на возврат" value={summaryQuery.data.refunds_detected} />
            <StatCard label="Кандидаты на дубликат" value={summaryQuery.data.duplicates_detected} />
          </div>

          <article className="card">
            <h3>Топ рискованных мерчантов</h3>
            {merchants.length > 0 ? (
              <table className="summary-table">
                <thead>
                  <tr><th>Мерчант</th><th>Алертов</th></tr>
                </thead>
                <tbody>
                  {merchants.map((merchant) => (
                    <tr
                      key={merchant.merchant}
                      onClick={() => navigate(`/graph?merchant=${encodeURIComponent(String(merchant.merchant))}`)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{merchant.merchant}</td>
                      <td>{merchant.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>Рискованные мерчанты не обнаружены.</p>
            )}
          </article>

          <div className="details-grid">
            {summaryQuery.data.refund_details?.length > 0 && (
              <article className="card">
                <h3>Детали возвратов</h3>
                <table className="summary-table">
                  <thead>
                    <tr><th>Мерчант</th><th>Сумма</th><th>Дата зачисления</th><th>Дата списания</th></tr>
                  </thead>
                  <tbody>
                    {summaryQuery.data.refund_details.map((r) => (
                      <tr key={`${r.credit_tx_id}-${r.debit_tx_id}`}>
                        <td>{r.merchant}</td>
                        <td>{formatMoney(r.amount)}</td>
                        <td>{r.credit_date}</td>
                        <td>{r.debit_date}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            )}

            {summaryQuery.data.duplicate_details?.length > 0 && (
              <article className="card">
                <h3>Детали дубликатов</h3>
                <table className="summary-table">
                  <thead>
                    <tr><th>Мерчант</th><th>Сумма</th><th>Интервал (мин)</th></tr>
                  </thead>
                  <tbody>
                    {summaryQuery.data.duplicate_details.map((d) => (
                      <tr key={`${d.tx1_id}-${d.tx2_id}`}>
                        <td>{d.merchant}</td>
                        <td>{formatMoney(d.amount)}</td>
                        <td>{d.time_gap_minutes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            )}
          </div>

          <article className="card">
            <h3>ИИ-анализ выписки</h3>
            <p style={{ color: "#94a3b8", fontSize: "0.85rem", margin: "0 0 12px" }}>
              Аналитическое заключение на основе данных выписки (DeepSeek v3.1)
            </p>
            {aiMutation.isIdle ? (
              <button
                className="primary-button"
                onClick={() => aiMutation.mutate()}
                type="button"
              >
                Запросить ИИ-анализ
              </button>
            ) : null}
            {aiMutation.isPending ? (
              <p style={{ color: "#60a5fa" }}>Анализирую выписку... Это может занять до минуты.</p>
            ) : null}
            {aiMutation.isError ? (
              <>
                <p className="text-danger">Ошибка ИИ-анализа: {String((aiMutation.error as Error)?.message ?? "Неизвестная ошибка")}</p>
                <button
                  className="primary-button"
                  onClick={() => aiMutation.mutate()}
                  style={{ marginTop: "8px" }}
                  type="button"
                >
                  Повторить
                </button>
              </>
            ) : null}
            {aiMutation.isSuccess ? (
              <div className="ai-analysis" dangerouslySetInnerHTML={{ __html: renderSimpleMarkdown(aiMutation.data.analysis) }} />
            ) : null}
          </article>

          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <button className="primary-button" onClick={() => navigate('/alerts')} type="button" style={{ margin: 0, flex: 1 }}>
              Перейти к алертам →
            </button>
            <button
              className="export-btn"
              onClick={handleExportCsv}
              type="button"
              style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "0.8rem", padding: "8px 14px", whiteSpace: "nowrap" }}
            >
              📥 CSV
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}

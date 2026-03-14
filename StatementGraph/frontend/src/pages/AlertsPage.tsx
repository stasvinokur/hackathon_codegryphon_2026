import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { getAlert, listAlerts, listTransactions, updateAlertStatus } from "../api/client";

const severities = ["all", "high", "medium", "low"] as const;

type SeverityFilter = (typeof severities)[number];

const SEVERITY_COLORS: Record<string, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#3b82f6",
};

const SEVERITY_LABELS: Record<string, string> = {
  all: "ВСЕ",
  high: "ВЫСОКИЙ",
  medium: "СРЕДНИЙ",
  low: "НИЗКИЙ",
};

const ALERT_TYPE_LABELS: Record<string, string> = {
  amount_anomaly: "Аномалия суммы",
  duplicate_candidate: "Дубликат",
  merchant_burst: "Всплеск мерчанта",
  refund_match: "Возврат",
  settlement_anomaly: "Задержка расчёта",
  merchant_hygiene: "Гигиена мерчанта",
  debt_dynamics: "Динамика долга",
  recurring_interval_anomaly: "Аномалия регулярности",
};

const STATUS_OPTIONS = ["new", "reviewed", "dismissed"] as const;

const STATUS_LABELS: Record<string, string> = {
  new: "новый",
  reviewed: "проверен",
  dismissed: "отклонён",
};

const RECOMMENDED_ACTIONS: Record<string, string> = {
  duplicate_candidate: "Проверьте обе транзакции и подтвердите, является ли одна дубликатом. При подтверждении — свяжитесь с мерчантом.",
  merchant_burst: "Проверьте, являются ли множественные списания легитимными (например, разделённые платежи) или мошеннической активностью.",
  refund_match: "Убедитесь, что сумма возврата соответствует исходному списанию и возврат ожидаем.",
  amount_anomaly: "Сравните сумму с типичными суммами мерчанта. Отметьте для ручной проверки если необъяснимо.",
  settlement_anomaly: "Проверьте, типична ли задержка расчёта для этого мерчанта.",
  merchant_hygiene: "Исследуйте идентификацию мерчанта — множественные алиасы могут указывать на обфускацию.",
  debt_dynamics: "Проверьте, соответствует ли рост задолженности реальным операциям.",
  recurring_interval_anomaly: "Проверьте, почему регулярный платёж был пропущен или задержан.",
  anomaly: "Проверьте детали транзакции на необычные паттерны. Рассмотрите эскалацию при высоком скоринге.",
};

const PAGE_SIZE = 15;

export function AlertsPage(): JSX.Element {
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const alertsQuery = useQuery({
    queryKey: ["alerts", severity],
    queryFn: () => listAlerts(severity === "all" ? undefined : severity),
  });

  const selectedAlertQuery = useQuery({
    enabled: Boolean(selectedAlertId),
    queryKey: ["alert-detail", selectedAlertId],
    queryFn: () => getAlert(selectedAlertId as string),
  });

  const relatedTxQuery = useQuery({
    enabled: Boolean(selectedAlertQuery.data?.transaction_id),
    queryKey: ["alert-related-txs", selectedAlertQuery.data?.transaction_id],
    queryFn: () => listTransactions(),
  });

  const statusMutation = useMutation({
    mutationFn: ({ alertId, status }: { alertId: string; status: string }) =>
      updateAlertStatus(alertId, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      if (selectedAlertId) {
        void queryClient.invalidateQueries({ queryKey: ["alert-detail", selectedAlertId] });
      }
    },
  });

  const alerts = useMemo(() => {
    let items = alertsQuery.data?.items ?? [];
    if (typeFilter !== "all") {
      items = items.filter((a) => a.alert_type === typeFilter);
    }
    const sorted = [...items].sort((a, b) => sortDir === "desc" ? b.score - a.score : a.score - b.score);
    return sorted;
  }, [alertsQuery.data?.items, typeFilter, sortDir]);

  const totalPages = Math.ceil(alerts.length / PAGE_SIZE);
  const pagedAlerts = alerts.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const relatedTransactions = useMemo(() => {
    if (!selectedAlertQuery.data || !relatedTxQuery.data) return [];
    const alertTx = relatedTxQuery.data.items.find(
      (tx) => tx.id === selectedAlertQuery.data?.transaction_id
    );
    if (!alertTx) return [];
    return relatedTxQuery.data.items
      .filter(
        (tx) =>
          tx.merchant_normalized === alertTx.merchant_normalized &&
          tx.id !== alertTx.id
      )
      .slice(0, 5);
  }, [selectedAlertQuery.data, relatedTxQuery.data]);

  function handleExportCsv() {
    const items = alertsQuery.data?.items ?? [];
    const lines = ["Критичность;Тип;Скоринг;Причина;Статус"];
    for (const a of items) {
      lines.push(`${a.severity};${ALERT_TYPE_LABELS[a.alert_type] ?? a.alert_type};${a.score};${a.reason.replaceAll(";", ",")};${a.status}`);
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "alerts_export.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="page">
      <h2>Панель алертов</h2>
      <p className="page-subtitle">Фильтрация по критичности и анализ причин каждого алерта.</p>

      <div className="card card-grid">
        <div>
          <label className="input-label" htmlFor="severity-filter">
            Фильтр критичности
          </label>
          <select
            id="severity-filter"
            onChange={(event) => { setSeverity(event.target.value as SeverityFilter); setPage(0); }}
            value={severity}
          >
            {severities.map((item) => (
              <option key={item} value={item}>
                {SEVERITY_LABELS[item] ?? item.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="input-label" htmlFor="type-filter">Фильтр типа</label>
          <select id="type-filter" onChange={(e) => { setTypeFilter(e.target.value); setPage(0); }} value={typeFilter}>
            <option value="all">ВСЕ ТИПЫ</option>
            <option value="amount_anomaly">Аномалия суммы</option>
            <option value="duplicate_candidate">Дубликат</option>
            <option value="merchant_burst">Всплеск мерчанта</option>
            <option value="refund_match">Возврат</option>
            <option value="settlement_anomaly">Задержка расчёта</option>
            <option value="merchant_hygiene">Гигиена мерчанта</option>
            <option value="debt_dynamics">Динамика долга</option>
            <option value="recurring_interval_anomaly">Аномалия регулярности</option>
          </select>
        </div>
      </div>

      <button className="export-btn" onClick={handleExportCsv} type="button">
        Экспорт CSV
      </button>

      {alertsQuery.isLoading ? <p>Загрузка алертов...</p> : null}
      {alertsQuery.isError ? <p className="text-danger">Ошибка загрузки алертов.</p> : null}

      <div className="alerts-layout">
        <div className="alerts-main">
          {alerts.length > 0 ? (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Критичность</th>
                    <th>Тип</th>
                    <th>Мерчант</th>
                    <th className="sortable-th" onClick={() => setSortDir(d => d === "desc" ? "asc" : "desc")}>
                      Скоринг {sortDir === "desc" ? "↓" : "↑"}
                    </th>
                    <th>Причина</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedAlerts.map((alert) => (
                    <tr
                      key={alert.id}
                      onClick={() => setSelectedAlertId(alert.id)}
                      className={selectedAlertId === alert.id ? "row--selected" : ""}
                    >
                      <td>
                        <span
                          className="severity-badge"
                          style={{ borderColor: SEVERITY_COLORS[alert.severity] ?? "#6b7280" }}
                        >
                          {SEVERITY_LABELS[alert.severity] ?? alert.severity.toUpperCase()}
                        </span>
                      </td>
                      <td>{ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}</td>
                      <td style={{ maxWidth: "120px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{alert.merchant_name ?? "—"}</td>
                      <td>{alert.score.toFixed(3)}</td>
                      <td>{alert.reason}</td>
                      <td>{STATUS_LABELS[alert.status] ?? alert.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {totalPages > 1 && (
                <div className="pagination">
                  <button className="status-btn" disabled={page === 0} onClick={() => setPage(p => p - 1)} type="button">← Назад</button>
                  <span>Стр. {page + 1} из {totalPages}</span>
                  <button className="status-btn" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} type="button">Далее →</button>
                </div>
              )}
            </div>
          ) : null}
        </div>

        <aside className={`alerts-sidebar ${selectedAlertQuery.data ? "" : "alerts-sidebar--empty"}`}>
          {selectedAlertQuery.data ? (
            <>
              <button
                className="sidebar-close"
                onClick={() => setSelectedAlertId(null)}
                type="button"
              >
                ×
              </button>

              <h3>Детали алерта</h3>

              <p><strong>Тип:</strong> {ALERT_TYPE_LABELS[selectedAlertQuery.data.alert_type] ?? selectedAlertQuery.data.alert_type}</p>
              <p>
                <strong>Критичность:</strong>{" "}
                <span style={{ color: SEVERITY_COLORS[selectedAlertQuery.data.severity] }}>
                  {SEVERITY_LABELS[selectedAlertQuery.data.severity] ?? selectedAlertQuery.data.severity.toUpperCase()}
                </span>
              </p>
              <p><strong>Скоринг:</strong> {selectedAlertQuery.data.score.toFixed(3)}</p>
              <p><strong>Причина:</strong> {selectedAlertQuery.data.reason}</p>

              <hr style={{ borderColor: "#334155", margin: "12px 0" }} />

              <p><strong>Рекомендация:</strong></p>
              <p className="recommended-action">
                {RECOMMENDED_ACTIONS[selectedAlertQuery.data.alert_type] ?? RECOMMENDED_ACTIONS.anomaly}
              </p>

              <button
                className="primary-button"
                onClick={() => navigate(`/graph?alert=${selectedAlertQuery.data!.id}`)}
                style={{ width: "100%", marginTop: "8px" }}
                type="button"
              >
                Показать на графе →
              </button>

              <hr style={{ borderColor: "#334155", margin: "12px 0" }} />

              <p><strong>Статус:</strong></p>
              <div className="status-actions">
                {STATUS_OPTIONS.map((st) => (
                  <button
                    key={st}
                    className={
                      selectedAlertQuery.data?.status === st
                        ? "status-btn status-btn--active"
                        : "status-btn"
                    }
                    disabled={statusMutation.isPending}
                    onClick={() =>
                      statusMutation.mutate({ alertId: selectedAlertQuery.data!.id, status: st })
                    }
                    type="button"
                  >
                    {STATUS_LABELS[st] ?? st}
                  </button>
                ))}
              </div>

              {relatedTransactions.length > 0 ? (
                <>
                  <hr style={{ borderColor: "#334155", margin: "12px 0" }} />
                  <h4>Связанные транзакции</h4>
                  <div className="table-wrapper">
                    <table className="data-table" style={{ fontSize: "0.8rem" }}>
                      <thead>
                        <tr>
                          <th>Дата</th>
                          <th>Сумма</th>
                          <th>Мерчант</th>
                        </tr>
                      </thead>
                      <tbody>
                        {relatedTransactions.map((tx) => (
                          <tr key={tx.id}>
                            <td>{tx.posted_at?.slice(0, 10) ?? "N/A"}</td>
                            <td>{tx.amount_signed_original}</td>
                            <td>{tx.merchant_normalized ?? tx.merchant_raw}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}

              <details style={{ marginTop: "12px" }}>
                <summary style={{ cursor: "pointer", color: "#94a3b8" }}>Объяснение (JSON)</summary>
                <pre className="json-block" style={{ fontSize: "0.7rem", marginTop: "8px" }}>
                  {JSON.stringify(selectedAlertQuery.data.explanation_json, null, 2)}
                </pre>
              </details>

              <p style={{ marginTop: "12px", fontSize: "0.75rem", color: "#64748b" }}>
                ID: {selectedAlertQuery.data.id.slice(0, 8)}...
              </p>
            </>
          ) : (
            <p style={{ color: "#64748b", textAlign: "center", marginTop: "40px" }}>
              Выберите алерт для просмотра деталей
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}

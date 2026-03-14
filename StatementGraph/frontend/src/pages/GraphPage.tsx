import { useCallback, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import CytoscapeComponent from "react-cytoscapejs";
import type cytoscape from "cytoscape";

import { getAlertGraph, getMerchantGraph } from "../api/client";

function toElements(nodes: Array<{ data: Record<string, unknown> }>, edges: Array<{ data: Record<string, unknown> }>) {
  return [...nodes, ...edges];
}

const NODE_COLORS: Record<string, string> = {
  Transaction: "#3b82f6",
  Merchant: "#10b981",
  Alert: "#ef4444",
  MerchantGroup: "#8b5cf6",
  Card: "#0ea5e9",
};

const EDGE_COLORS: Record<string, string> = {
  FLAGS: "#ef4444",
  POSSIBLE_DUPLICATE_OF: "#f59e0b",
  POSSIBLE_REFUND_FOR: "#22c55e",
  BURST_WITHIN_WINDOW: "#f97316",
  AT_ALIAS: "#6b7280",
  CONTAINS: "#6b7280",
  IN_GROUP: "#8b5cf6",
  HAS_CARD: "#0ea5e9",
  SIMILAR_AMOUNT_PATTERN: "#a855f7",
};

const NODE_TYPE_LABELS: Record<string, string> = {
  Transaction: "Транзакция",
  Merchant: "Мерчант",
  Alert: "Алерт",
  MerchantGroup: "Группа мерчантов",
  Card: "Карта",
};

interface NodeDetail {
  id: string;
  nodeType: string;
  [key: string]: unknown;
}

export function GraphPage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const [alertId, setAlertId] = useState(() => searchParams.get("alert") ?? "");
  const [merchantId, setMerchantId] = useState(() => searchParams.get("merchant") ?? "");
  const [appliedAlertId, setAppliedAlertId] = useState(() => searchParams.get("alert") ?? "");
  const [appliedMerchantId, setAppliedMerchantId] = useState(() => searchParams.get("merchant") ?? "");
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  function handleLoadGraph() {
    setAppliedAlertId(alertId);
    setAppliedMerchantId(merchantId);
  }

  const alertGraphQuery = useQuery({
    enabled: Boolean(appliedAlertId),
    queryKey: ["graph-alert", appliedAlertId],
    queryFn: () => getAlertGraph(appliedAlertId),
  });

  const merchantGraphQuery = useQuery({
    enabled: Boolean(appliedMerchantId),
    queryKey: ["graph-merchant", appliedMerchantId],
    queryFn: () => getMerchantGraph(appliedMerchantId),
  });

  const activeGraph = useMemo(() => {
    const m = merchantGraphQuery.data;
    const a = alertGraphQuery.data;
    if (m && m.nodes.length > 0) return m;
    if (a && a.nodes.length > 0) return a;
    return null;
  }, [merchantGraphQuery.data, alertGraphQuery.data]);

  const elements = useMemo(
    () => toElements(activeGraph?.nodes ?? [], activeGraph?.edges ?? []),
    [activeGraph?.edges, activeGraph?.nodes],
  );

  const handleCyInit = useCallback((cy: cytoscape.Core) => {
    cyRef.current = cy;
    cy.on("tap", "node", (event) => {
      const node = event.target;
      setSelectedNode(node.data() as NodeDetail);
    });
    cy.on("tap", (event) => {
      if (event.target === cy) {
        setSelectedNode(null);
      }
    });
  }, []);

  return (
    <section className="page">
      <h2>Граф расследования</h2>
      <p className="page-subtitle">Визуализация подозрительных связей вокруг алерта или мерчанта.</p>

      <div className="card card-grid">
        <div>
          <label className="input-label" htmlFor="graph-alert-id">
            ID алерта
          </label>
          <input
            id="graph-alert-id"
            onChange={(event) => setAlertId(event.target.value.trim())}
            placeholder="Вставьте UUID алерта"
            type="text"
            value={alertId}
          />
        </div>
        <div>
          <label className="input-label" htmlFor="graph-merchant-id">
            Имя мерчанта
          </label>
          <input
            id="graph-merchant-id"
            onChange={(event) => setMerchantId(event.target.value.trim())}
            placeholder="Нормализованный мерчант"
            type="text"
            value={merchantId}
          />
        </div>
        <div style={{ display: "flex", alignItems: "flex-end" }}>
          <button
            className="primary-button"
            disabled={!alertId && !merchantId}
            onClick={handleLoadGraph}
            type="button"
            style={{ marginTop: 0 }}
          >
            Загрузить граф
          </button>
        </div>
      </div>

      {alertGraphQuery.isLoading || merchantGraphQuery.isLoading ? <p>Загрузка графа...</p> : null}
      {alertGraphQuery.isError || merchantGraphQuery.isError ? (
        <p className="text-danger">Не удалось загрузить данные графа для указанной сущности.</p>
      ) : null}

      {elements.length > 0 ? (
        <>
          <div className="graph-legend card">
            <strong>Легенда: </strong>
            <span style={{ color: "#ef4444" }}>Алерт </span>
            <span style={{ color: "#3b82f6" }}>Транзакция </span>
            <span style={{ color: "#10b981" }}>Мерчант </span>
            <span style={{ color: "#8b5cf6" }}>Группа </span>
            <span style={{ color: "#0ea5e9" }}>Карта </span>
            <span style={{ color: "#f59e0b" }}>Дубликат </span>
            <span style={{ color: "#f97316" }}>Всплеск </span>
            <span style={{ color: "#22c55e" }}>Возврат </span>
            <span style={{ color: "#a855f7" }}>Похожая сумма</span>
          </div>
          <div className="graph-wrapper card" style={{ height: "calc(100vh - 300px)", minHeight: "500px" }}>
            <CytoscapeComponent
              cy={handleCyInit}
              elements={elements}
              layout={{ name: "cose", animate: false }}
              style={{ width: "100%", height: "100%" }}
              stylesheet={[
                /* Generic selectors FIRST — specific ones override below */
                {
                  selector: "node",
                  style: {
                    "background-color": "#64748b",
                    color: "#ffffff",
                    label: "data(label)",
                    "font-size": 10,
                    "text-wrap": "wrap",
                  },
                },
                {
                  selector: "edge",
                  style: {
                    width: 1,
                    "line-color": "#6b7280",
                    "target-arrow-color": "#6b7280",
                    "target-arrow-shape": "triangle",
                    "curve-style": "bezier",
                  },
                },
                /* Specific node types */
                {
                  selector: "node[nodeType='Transaction']",
                  style: {
                    "background-color": NODE_COLORS.Transaction,
                    "font-size": 10,
                    width: 28,
                    height: 28,
                  },
                },
                {
                  selector: "node[nodeType='Merchant']",
                  style: {
                    "background-color": NODE_COLORS.Merchant,
                    "font-size": 11,
                    shape: "round-rectangle",
                    width: 40,
                    height: 40,
                    "text-valign": "bottom",
                    "text-margin-y": 5,
                  },
                },
                {
                  selector: "node[nodeType='Alert']",
                  style: {
                    "background-color": NODE_COLORS.Alert,
                    "font-size": 11,
                    shape: "diamond",
                    width: 35,
                    height: 35,
                  },
                },
                {
                  selector: "node[nodeType='MerchantGroup']",
                  style: {
                    "background-color": NODE_COLORS.MerchantGroup,
                    "font-size": 11,
                    shape: "hexagon",
                    width: 45,
                    height: 45,
                    "text-valign": "bottom",
                    "text-margin-y": 5,
                  },
                },
                {
                  selector: "node[nodeType='Card']",
                  style: {
                    "background-color": NODE_COLORS.Card,
                    "font-size": 11,
                    shape: "round-rectangle",
                    width: 50,
                    height: 30,
                  },
                },
                /* Specific edge types */
                {
                  selector: "edge[type='FLAGS']",
                  style: { width: 3, "line-color": EDGE_COLORS.FLAGS, "target-arrow-color": EDGE_COLORS.FLAGS },
                },
                {
                  selector: "edge[type='POSSIBLE_DUPLICATE_OF']",
                  style: { width: 2, "line-color": EDGE_COLORS.POSSIBLE_DUPLICATE_OF, "target-arrow-color": EDGE_COLORS.POSSIBLE_DUPLICATE_OF, "line-style": "dashed" },
                },
                {
                  selector: "edge[type='POSSIBLE_REFUND_FOR']",
                  style: { width: 2, "line-color": EDGE_COLORS.POSSIBLE_REFUND_FOR, "target-arrow-color": EDGE_COLORS.POSSIBLE_REFUND_FOR, "line-style": "dashed" },
                },
                {
                  selector: "edge[type='BURST_WITHIN_WINDOW']",
                  style: { width: 2, "line-color": EDGE_COLORS.BURST_WITHIN_WINDOW, "target-arrow-color": EDGE_COLORS.BURST_WITHIN_WINDOW, "line-style": "dotted" },
                },
                {
                  selector: "edge[type='SIMILAR_AMOUNT_PATTERN']",
                  style: { width: 2, "line-color": EDGE_COLORS.SIMILAR_AMOUNT_PATTERN, "target-arrow-color": EDGE_COLORS.SIMILAR_AMOUNT_PATTERN, "line-style": "dotted" },
                },
                {
                  selector: "edge[type='IN_GROUP']",
                  style: { width: 1, "line-color": EDGE_COLORS.IN_GROUP, "target-arrow-color": EDGE_COLORS.IN_GROUP },
                },
                {
                  selector: "edge[type='HAS_CARD']",
                  style: { width: 1, "line-color": EDGE_COLORS.HAS_CARD, "target-arrow-color": EDGE_COLORS.HAS_CARD },
                },
              ]}
            />
          </div>

          {selectedNode ? (
            <div className="node-detail card">
              <h3>{NODE_TYPE_LABELS[selectedNode.nodeType] ?? selectedNode.nodeType}: {selectedNode.label as string ?? selectedNode.id}</h3>
              <div className="metadata-grid">
                {Object.entries(selectedNode)
                  .filter(([key]) => key !== "id" && key !== "label")
                  .map(([key, value]) => (
                    <><span className="meta-label" key={`${key}-label`}>{key}</span><span key={`${key}-value`}>{String(value)}</span></>
                  ))}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <p className="card">Введите ID алерта или имя мерчанта для отображения графа связей.</p>
      )}
    </section>
  );
}

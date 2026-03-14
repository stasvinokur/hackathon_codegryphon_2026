export interface StatementOut {
  id: string;
  bank_name: string | null;
  product_type: string | null;
  masked_card_number: string | null;
  statement_period_start: string | null;
  statement_period_end: string | null;
  source_filename: string;
  uploaded_at: string;
}

export interface StatementUploadResponse {
  statement: StatementOut;
}

export interface StatementActionResponse {
  statement_id: string;
  status: string;
  details: Record<string, number | string>;
  statement?: StatementOut | null;
}

export interface StatementSummaryResponse {
  statement_id: string;
  total_operations: number;
  total_inflow: string;
  total_outflow: string;
  suspicious_alerts: number;
  top_risky_merchants: Array<{ merchant: string; count: number }>;
  refunds_detected: number;
  duplicates_detected: number;
}

export interface TransactionOut {
  id: string;
  statement_id: string;
  posted_at: string | null;
  processed_at: string | null;
  amount_signed_original: string;
  currency_original: string;
  inflow_amount: string;
  outflow_amount: string;
  merchant_raw: string;
  merchant_normalized: string | null;
  operation_type: string;
  risk_score: string;
  anomaly_score: string;
}

export interface TransactionListResponse {
  items: TransactionOut[];
  total: number;
}

export interface AlertOut {
  id: string;
  transaction_id: string;
  severity: string;
  alert_type: string;
  status: string;
  score: number;
  reason: string;
  explanation_json: Record<string, unknown>;
  created_at: string;
  merchant_name: string | null;
}

export interface AlertListResponse {
  items: AlertOut[];
  total: number;
}

export interface GraphNode {
  data: Record<string, unknown>;
}

export interface GraphEdge {
  data: Record<string, unknown>;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

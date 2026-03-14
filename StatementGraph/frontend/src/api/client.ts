import axios from "axios";

import type {
  AlertListResponse,
  AlertOut,
  GraphResponse,
  StatementActionResponse,
  StatementSummaryResponse,
  StatementUploadResponse,
  TransactionListResponse,
} from "./types";

const baseURL =
  import.meta.env.VITE_API_BASE_URL?.toString().trim() || "http://localhost:8000/api/v1";

export const apiClient = axios.create({
  baseURL,
  timeout: 20000,
});

export async function uploadStatementPdf(file: File): Promise<StatementUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post<StatementUploadResponse>("/statements/upload-pdf", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function parseStatement(statementId: string): Promise<StatementActionResponse> {
  const response = await apiClient.post<StatementActionResponse>(`/statements/${statementId}/parse`);
  return response.data;
}

export async function normalizeStatement(statementId: string): Promise<StatementActionResponse> {
  const response = await apiClient.post<StatementActionResponse>(`/statements/${statementId}/normalize`);
  return response.data;
}

export async function scoreStatement(statementId: string): Promise<StatementActionResponse> {
  const response = await apiClient.post<StatementActionResponse>(`/statements/${statementId}/score`);
  return response.data;
}

export async function getStatementSummary(statementId: string): Promise<StatementSummaryResponse> {
  const response = await apiClient.get<StatementSummaryResponse>(`/statements/${statementId}/summary`);
  return response.data;
}

export async function clearAllData(): Promise<void> {
  await apiClient.delete("/statements/all");
}

export async function listAlerts(severity?: string): Promise<AlertListResponse> {
  const response = await apiClient.get<AlertListResponse>("/alerts", {
    params: severity ? { severity } : undefined,
  });
  return response.data;
}

export async function getAlert(alertId: string): Promise<AlertOut> {
  const response = await apiClient.get<AlertOut>(`/alerts/${alertId}`);
  return response.data;
}

export async function listTransactions(statementId?: string): Promise<TransactionListResponse> {
  const response = await apiClient.get<TransactionListResponse>("/transactions", {
    params: statementId ? { statement_id: statementId } : undefined,
  });
  return response.data;
}

export async function getAlertGraph(alertId: string): Promise<GraphResponse> {
  const response = await apiClient.get<GraphResponse>(`/graph/alert/${alertId}`);
  return response.data;
}

export async function getMerchantGraph(merchantId: string): Promise<GraphResponse> {
  const response = await apiClient.get<GraphResponse>(`/graph/merchant/${merchantId}`);
  return response.data;
}

export async function updateAlertStatus(alertId: string, status: string): Promise<AlertOut> {
  const response = await apiClient.patch<AlertOut>(`/alerts/${alertId}`, { status });
  return response.data;
}

export async function getAiAnalysis(statementId: string): Promise<{ analysis: string }> {
  const response = await apiClient.get<{ analysis: string }>(`/statements/${statementId}/ai-analysis`, {
    timeout: 120000,
  });
  return response.data;
}

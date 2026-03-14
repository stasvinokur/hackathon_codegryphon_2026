import { useCallback, useMemo, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  clearAllData,
  normalizeStatement,
  parseStatement,
  scoreStatement,
  uploadStatementPdf,
} from "../api/client";
import { LAST_STATEMENT_STORAGE_KEY } from "../constants";

const UPLOAD_STATE_KEY = "statementgraph:uploadState";

interface UploadPipelineResult {
  statementId: string;
  rowsParsed: number;
  rowsNormalized: number;
  alertsCreated: number;
  bankName: string | null;
  productType: string | null;
  maskedCard: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  sourceFilename: string;
}

function loadSavedResult(): UploadPipelineResult | null {
  try {
    const raw = localStorage.getItem(UPLOAD_STATE_KEY);
    return raw ? (JSON.parse(raw) as UploadPipelineResult) : null;
  } catch {
    return null;
  }
}

export function UploadPage(): JSX.Element {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [savedResult, setSavedResult] = useState<UploadPipelineResult | null>(loadSavedResult);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const pipelineMutation = useMutation<UploadPipelineResult, Error>({
    mutationFn: async () => {
      if (!file) {
        throw new Error("Выберите PDF-файл выписки");
      }

      const uploadResponse = await uploadStatementPdf(file);
      const statementId = uploadResponse.statement.id;

      const parseResponse = await parseStatement(statementId);
      const normalizeResponse = await normalizeStatement(statementId);
      const scoreResponse = await scoreStatement(statementId);

      localStorage.setItem(LAST_STATEMENT_STORAGE_KEY, statementId);

      const result: UploadPipelineResult = {
        statementId,
        rowsParsed: Number(parseResponse.details.rows ?? 0),
        rowsNormalized: Number(normalizeResponse.details.rows ?? 0),
        alertsCreated: Number(scoreResponse.details.alerts ?? 0),
        bankName: parseResponse.statement?.bank_name ?? uploadResponse.statement.bank_name ?? null,
        productType: parseResponse.statement?.product_type ?? uploadResponse.statement.product_type ?? null,
        maskedCard: parseResponse.statement?.masked_card_number ?? uploadResponse.statement.masked_card_number ?? null,
        periodStart: parseResponse.statement?.statement_period_start ?? uploadResponse.statement.statement_period_start ?? null,
        periodEnd: parseResponse.statement?.statement_period_end ?? uploadResponse.statement.statement_period_end ?? null,
        sourceFilename: uploadResponse.statement.source_filename,
      };
      localStorage.setItem(UPLOAD_STATE_KEY, JSON.stringify(result));
      setSavedResult(result);
      return result;
    },
  });

  const resultData = pipelineMutation.data ?? savedResult;

  const statusMessage = useMemo(() => {
    if (pipelineMutation.isPending) {
      return "Обработка: загрузка → парсинг → нормализация → скоринг";
    }
    if (pipelineMutation.isError) {
      return pipelineMutation.error.message;
    }
    if (resultData) {
      return "Выписка обработана и готова к анализу.";
    }
    return "Загрузите PDF-выписку для начала анализа.";
  }, [
    pipelineMutation.error?.message,
    pipelineMutation.isError,
    pipelineMutation.isPending,
    resultData,
  ]);

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    const droppedFile = event.dataTransfer.files[0];
    if (droppedFile?.type === "application/pdf") {
      setFile(droppedFile);
    }
  }, []);

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  return (
    <section className="page">
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <h2 style={{ margin: 0 }}>Загрузка и обработка выписки</h2>
        {resultData ? (
          <button
            title="Новая выписка"
            onClick={async () => {
              await clearAllData();
              localStorage.removeItem(UPLOAD_STATE_KEY);
              localStorage.removeItem(LAST_STATEMENT_STORAGE_KEY);
              setSavedResult(null);
              setFile(null);
              pipelineMutation.reset();
              queryClient.removeQueries();
            }}
            type="button"
            style={{
              background: "none",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              cursor: "pointer",
              padding: "4px 8px",
              fontSize: "18px",
              lineHeight: 1,
              color: "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <span style={{ fontSize: "16px" }}>+</span>
            <span style={{ fontSize: "12px" }}>Новая</span>
          </button>
        ) : null}
      </div>
      <p className="page-subtitle">{statusMessage}</p>

      <div className="card">
        <input
          accept="application/pdf"
          id="statement-file"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          ref={fileInputRef}
          style={{ display: "none" }}
          type="file"
        />
        <div
          className={`dropzone ${isDragging ? "dropzone--active" : ""} ${file ? "dropzone--has-file" : ""}`}
          onClick={() => fileInputRef.current?.click()}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onKeyDown={(e) => { if (e.key === "Enter") fileInputRef.current?.click(); }}
          role="button"
          tabIndex={0}
        >
          {file ? (
            <p>{file.name}</p>
          ) : (
            <p>Перетащите PDF-файл сюда или нажмите для выбора</p>
          )}
        </div>

        <button
          className="primary-button"
          disabled={!file || pipelineMutation.isPending}
          onClick={() => pipelineMutation.mutate()}
          type="button"
        >
          {pipelineMutation.isPending ? "Обработка..." : "Запустить анализ"}
        </button>
      </div>

      {resultData ? (
        <>
          <div className="card card--success">
            <h3>Результат обработки</h3>
            <ul>
              <li>ID выписки: {resultData.statementId.slice(0, 8)}...</li>
              <li>Распарсено строк: {resultData.rowsParsed}</li>
              <li>Нормализовано строк: {resultData.rowsNormalized}</li>
              <li>Создано алертов: {resultData.alertsCreated}</li>
            </ul>
          </div>

          <div className="card">
            <h3>Метаданные выписки</h3>
            <div className="metadata-grid">
              <span className="meta-label">Банк</span><span>{resultData.bankName ?? "—"}</span>
              <span className="meta-label">Продукт</span><span>{resultData.productType ?? "—"}</span>
              <span className="meta-label">Номер карты</span><span>{resultData.maskedCard ?? "—"}</span>
              <span className="meta-label">Период</span><span>{resultData.periodStart ?? "—"} — {resultData.periodEnd ?? "—"}</span>
              <span className="meta-label">Файл</span><span>{resultData.sourceFilename}</span>
            </div>
          </div>

          <button
            className="primary-button"
            onClick={() => navigate('/summary')}
            type="button"
          >
            Перейти к сводке →
          </button>
        </>
      ) : null}
    </section>
  );
}

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.alert import Alert
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.repositories.alert_repository import AlertRepository
from app.repositories.statement_repository import StatementRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.statement import DuplicateDetail, RefundDetail, StatementSummaryResponse
from app.services.detection.risk_engine import RiskEngine
from app.services.graph.graph_builder import GraphBuilderService
from app.services.normalization.normalizer import StatementNormalizer
from app.services.parsers.statement_pdf_parser import StatementPdfParser


class StatementWorkflowService:
    """Orchestrates statement ingestion and investigation pipeline steps."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._settings = get_settings()
        self._statement_repo = StatementRepository(session)
        self._transaction_repo = TransactionRepository(session)
        self._alert_repo = AlertRepository(session)
        self._parser = StatementPdfParser()
        self._normalizer = StatementNormalizer()
        self._risk_engine = RiskEngine()
        self._graph_builder = GraphBuilderService(session)

    def clear_all_data(self) -> None:
        """Remove all existing statements, transactions and alerts (single-statement mode)."""
        self._session.query(Alert).delete()
        self._session.query(Transaction).delete()
        self._session.query(Statement).delete()
        self._session.commit()

    async def upload_statement(self, file: UploadFile) -> Statement:
        file_name = file.filename or ""
        if not file_name.lower().endswith(".pdf"):
            raise ValueError("Only PDF files are supported")

        payload = await file.read()
        if not payload:
            raise ValueError("Uploaded file is empty")

        max_size_bytes = self._settings.max_upload_size_mb * 1024 * 1024
        if len(payload) > max_size_bytes:
            raise ValueError("Uploaded file exceeds maximum allowed size")

        # Single-statement mode: clear previous data before new upload
        self.clear_all_data()

        upload_dir = self._settings.ensure_upload_dir()
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        safe_name = f"{timestamp}_{Path(file_name).name}"
        destination = upload_dir / safe_name
        destination.write_bytes(payload)

        statement = Statement(
            source_filename=file_name or safe_name,
            source_file_path=str(destination),
        )
        return self._statement_repo.create(statement)

    def parse_statement(self, statement_id: UUID) -> int:
        statement = self._require_statement(statement_id)

        # Extract and populate statement metadata
        metadata = self._parser.parse_statement_metadata(statement.source_file_path)
        if metadata:
            statement.bank_name = metadata.get("bank_name", statement.bank_name)
            statement.product_type = metadata.get("product_type", statement.product_type)
            statement.masked_card_number = metadata.get("masked_card_number", statement.masked_card_number)
            statement.statement_period_start = metadata.get("statement_period_start", statement.statement_period_start)
            statement.statement_period_end = metadata.get("statement_period_end", statement.statement_period_end)
            statement.credit_limit = metadata.get("credit_limit", statement.credit_limit)
            statement.available_balance = metadata.get("available_balance", statement.available_balance)
            statement.debt_total = metadata.get("debt_total", statement.debt_total)
            statement.minimum_payment = metadata.get("minimum_payment", statement.minimum_payment)
            statement.grace_period_status = metadata.get("grace_period_status", statement.grace_period_status)
            self._session.add(statement)
            self._session.commit()

        rows = self._parser.parse_transactions(statement.source_file_path)

        transactions = [
            Transaction(
                statement_id=statement.id,
                posted_at=row.get("posted_at"),
                processed_at=row.get("processed_at"),
                settlement_lag_hours=Decimal(str(row.get("settlement_lag_hours", 0))),
                amount_signed_original=Decimal(str(row.get("amount_signed_original", 0))),
                currency_original=str(row.get("currency_original", "RUB")),
                currency_normalized=str(row.get("currency_original", "RUB")),
                inflow_amount=Decimal(str(row.get("inflow_amount", 0))),
                outflow_amount=Decimal(str(row.get("outflow_amount", 0))),
                fee_amount=Decimal(str(row.get("fee_amount", 0))),
                debt_after_transaction=Decimal(str(row["debt_after_transaction"])) if row.get("debt_after_transaction") is not None else None,
                description_raw=str(row.get("description_raw", "")),
                description_clean=str(row.get("description_clean", "")),
                merchant_raw=str(row.get("merchant_raw", "UNKNOWN")),
                merchant_normalized=str(row.get("merchant_raw", "UNKNOWN")),
                operation_type="credit" if row.get("is_credit") else "debit",
                is_credit=bool(row.get("is_credit", False)),
                raw_row_json=self._make_json_safe(row),
                explanation_json={},
            )
            for row in rows
        ]
        self._transaction_repo.replace_for_statement(statement.id, transactions)
        return len(transactions)

    @staticmethod
    def _parse_dt(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def normalize_statement(self, statement_id: UUID) -> int:
        statement = self._require_statement(statement_id)
        transactions = self._transaction_repo.list(statement.id)
        normalized_rows = self._normalizer.normalize_rows([tx.raw_row_json for tx in transactions])

        normalized_models = [
            Transaction(
                statement_id=statement.id,
                posted_at=self._parse_dt(row.get("posted_at")),
                processed_at=self._parse_dt(row.get("processed_at")),
                settlement_lag_hours=Decimal(str(row.get("settlement_lag_hours", 0))),
                amount_signed_original=Decimal(str(row.get("amount_signed_original", 0))),
                currency_original=str(row.get("currency_original", "RUB")),
                currency_normalized=str(row.get("currency_normalized", "RUB")),
                inflow_amount=Decimal(str(row.get("inflow_amount", 0))),
                outflow_amount=Decimal(str(row.get("outflow_amount", 0))),
                fee_amount=Decimal(str(row.get("fee_amount", 0))),
                debt_after_transaction=Decimal(str(row["debt_after_transaction"])) if row.get("debt_after_transaction") is not None else None,
                description_raw=str(row.get("description_raw", "")),
                description_clean=str(row.get("description_clean", "")),
                merchant_raw=str(row.get("merchant_raw", "UNKNOWN")),
                merchant_normalized=str(row.get("merchant_normalized", "UNKNOWN")),
                merchant_group=row.get("merchant_group"),
                operation_type=str(row.get("operation_type", "debit")),
                is_credit=bool(row.get("is_credit", False)),
                is_refund_candidate=bool(row.get("is_refund_candidate", False)),
                is_duplicate_candidate=bool(row.get("is_duplicate_candidate", False)),
                is_burst_candidate=bool(row.get("is_burst_candidate", False)),
                raw_row_json=self._make_json_safe(row),
                explanation_json={},
            )
            for row in normalized_rows
        ]
        self._transaction_repo.replace_for_statement(statement.id, normalized_models)
        return len(normalized_models)

    def score_statement(self, statement_id: UUID) -> int:
        statement = self._require_statement(statement_id)
        transactions = self._transaction_repo.list(statement.id)
        scored_alerts = self._risk_engine.score(transactions)
        alert_models = self._risk_engine.to_alert_models(scored_alerts)

        self._session.add_all(transactions)
        self._alert_repo.replace_for_transaction_ids([tx.id for tx in transactions], alert_models)
        self._session.commit()
        self._graph_builder.sync_statement_graph(statement.id)
        return len(alert_models)

    def rebuild_merchant_resolution(self) -> int:
        transactions = self._transaction_repo.list()
        updated = 0
        for transaction in transactions:
            normalized = self._normalizer.normalize_merchant(transaction.merchant_raw)
            transaction.merchant_normalized = normalized.normalized_merchant_name
            transaction.merchant_group = normalized.merchant_group
            updated += 1
        self._session.add_all(transactions)
        self._session.commit()
        return updated

    def build_summary(self, statement_id: UUID) -> StatementSummaryResponse:
        statement = self._require_statement(statement_id)
        transactions = self._transaction_repo.list(statement.id)
        alerts = self._alert_repo.list_by_statement(statement_id)
        alert_by_tx = {alert.transaction_id for alert in alerts}

        total_inflow = sum((tx.inflow_amount for tx in transactions), Decimal("0"))
        total_outflow = sum((tx.outflow_amount for tx in transactions), Decimal("0"))

        merchant_risk: Counter[str] = Counter()
        for tx in transactions:
            if tx.id in alert_by_tx:
                merchant_risk[tx.merchant_normalized or "UNKNOWN"] += 1

        top_merchants = [
            {"merchant": merchant, "count": float(count)}
            for merchant, count in merchant_risk.most_common(5)
        ]

        refund_details = self._find_refund_pairs(transactions)
        duplicate_details = self._find_duplicate_pairs(transactions)

        return StatementSummaryResponse(
            statement_id=statement.id,
            total_operations=len(transactions),
            total_inflow=total_inflow,
            total_outflow=total_outflow,
            suspicious_alerts=len(alerts),
            top_risky_merchants=top_merchants,
            refunds_detected=sum(1 for tx in transactions if tx.is_refund_candidate),
            duplicates_detected=sum(1 for tx in transactions if tx.is_duplicate_candidate),
            refund_details=refund_details,
            duplicate_details=duplicate_details,
        )

    @staticmethod
    def _match_refund(cr: Transaction, debits: list[Transaction], used: set[UUID]) -> RefundDetail | None:
        amt = abs(cr.amount_signed_original)
        tol = amt * Decimal("0.1")
        for db in debits:
            if db.id in used or db.posted_at >= cr.posted_at:  # type: ignore[operator]
                continue
            if db.merchant_normalized != cr.merchant_normalized:
                continue
            if abs(abs(db.amount_signed_original) - amt) <= tol:
                used.add(db.id)
                return RefundDetail(
                    credit_tx_id=cr.id, debit_tx_id=db.id, amount=amt,
                    merchant=cr.merchant_normalized or "UNKNOWN",
                    credit_date=cr.posted_at.strftime("%Y-%m-%d %H:%M"),  # type: ignore[union-attr]
                    debit_date=db.posted_at.strftime("%Y-%m-%d %H:%M"),  # type: ignore[union-attr]
                )
        return None

    @staticmethod
    def _find_refund_pairs(transactions: list[Transaction]) -> list[RefundDetail]:
        credit_txs = [tx for tx in transactions if tx.is_credit and tx.posted_at]
        debit_txs = [tx for tx in transactions if not tx.is_credit and tx.posted_at]
        used_debits: set[UUID] = set()
        pairs: list[RefundDetail] = []
        for cr in credit_txs:
            match = StatementWorkflowService._match_refund(cr, debit_txs, used_debits)
            if match:
                pairs.append(match)
        return pairs

    @staticmethod
    def _find_duplicate_pairs(transactions: list[Transaction]) -> list[DuplicateDetail]:
        pairs: list[DuplicateDetail] = []
        debits = [tx for tx in transactions if not tx.is_credit and tx.posted_at]
        debits.sort(key=lambda t: t.posted_at)  # type: ignore[arg-type,return-value]
        for i, a in enumerate(debits):
            for b in debits[i + 1:]:
                if a.merchant_normalized != b.merchant_normalized:
                    continue
                if a.amount_signed_original != b.amount_signed_original:
                    continue
                gap = abs((b.posted_at - a.posted_at).total_seconds()) / 60  # type: ignore[operator]
                if gap <= 30:
                    pairs.append(DuplicateDetail(
                        tx1_id=a.id, tx2_id=b.id,
                        amount=abs(a.amount_signed_original),
                        merchant=a.merchant_normalized or "UNKNOWN",
                        time_gap_minutes=round(gap, 1),
                    ))
        return pairs

    @staticmethod
    def _make_json_safe(data: dict) -> dict:
        """Convert non-JSON-serializable values (datetime, Decimal) to strings."""
        safe: dict = {}
        for k, v in data.items():
            if isinstance(v, datetime):
                safe[k] = v.isoformat()
            elif isinstance(v, Decimal):
                safe[k] = str(v)
            else:
                safe[k] = v
        return safe

    def _require_statement(self, statement_id: UUID) -> Statement:
        statement = self._statement_repo.get(statement_id)
        if statement is None:
            raise ValueError("Statement not found")
        return statement

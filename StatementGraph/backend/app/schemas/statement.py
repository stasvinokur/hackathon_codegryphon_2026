from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StatementOut(BaseModel):
    """Statement metadata response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bank_name: str | None = None
    product_type: str | None = None
    masked_card_number: str | None = None
    statement_period_start: date | None = None
    statement_period_end: date | None = None
    source_filename: str
    uploaded_at: datetime


class StatementUploadResponse(BaseModel):
    """Upload response payload."""

    statement: StatementOut


class StatementActionResponse(BaseModel):
    """Operation status payload for pipeline steps."""

    statement_id: UUID
    status: str
    details: dict[str, int | float | str]
    statement: StatementOut | None = None


class RefundDetail(BaseModel):
    credit_tx_id: UUID
    debit_tx_id: UUID
    amount: Decimal
    merchant: str
    credit_date: str
    debit_date: str


class DuplicateDetail(BaseModel):
    tx1_id: UUID
    tx2_id: UUID
    amount: Decimal
    merchant: str
    time_gap_minutes: float


class StatementSummaryResponse(BaseModel):
    """Aggregated summary for statement investigation."""

    statement_id: UUID
    total_operations: int
    total_inflow: Decimal
    total_outflow: Decimal
    suspicious_alerts: int
    top_risky_merchants: list[dict[str, str | float]]
    refunds_detected: int
    duplicates_detected: int
    refund_details: list[RefundDetail] = []
    duplicate_details: list[DuplicateDetail] = []

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    """Transaction response model used in list and detail views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    statement_id: UUID
    posted_at: datetime | None
    processed_at: datetime | None
    amount_signed_original: Decimal
    currency_original: str
    inflow_amount: Decimal
    outflow_amount: Decimal
    merchant_raw: str
    merchant_normalized: str | None
    operation_type: str
    risk_score: Decimal
    anomaly_score: Decimal


class TransactionListResponse(BaseModel):
    """Paginated transaction list response."""

    items: list[TransactionOut]
    total: int

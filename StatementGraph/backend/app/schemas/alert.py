from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    """Serialized alert record for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    severity: str
    alert_type: str
    status: str
    score: float
    reason: str
    explanation_json: dict
    created_at: datetime
    merchant_name: str | None = None


class AlertUpdateRequest(BaseModel):
    """Request body for updating an alert status."""

    status: str


class AlertListResponse(BaseModel):
    """Paginated alert list response."""

    items: list[AlertOut]
    total: int

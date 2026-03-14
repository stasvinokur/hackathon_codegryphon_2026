from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertListResponse, AlertOut, AlertUpdateRequest

router = APIRouter()
DBSessionDep = Annotated[Session, Depends(get_db_session)]


def _alert_to_out(alert: object) -> AlertOut:
    out = AlertOut.model_validate(alert)
    if hasattr(alert, "transaction") and alert.transaction is not None:  # type: ignore[union-attr]
        out.merchant_name = alert.transaction.merchant_normalized  # type: ignore[union-attr]
    return out


@router.get("", response_model=AlertListResponse)
def list_alerts(
    session: DBSessionDep,
    severity: Annotated[str | None, Query()] = None,
) -> AlertListResponse:
    repository = AlertRepository(session)
    alerts = repository.list(severity=severity)
    return AlertListResponse(
        items=[_alert_to_out(item) for item in alerts],
        total=len(alerts),
    )


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: UUID, session: DBSessionDep) -> AlertOut:
    repository = AlertRepository(session)
    alert = repository.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _alert_to_out(alert)


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert_status(
    alert_id: UUID,
    body: AlertUpdateRequest,
    session: DBSessionDep,
) -> AlertOut:
    """Update alert status (new → reviewed → dismissed)."""
    valid_statuses = {"new", "reviewed", "dismissed"}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid_statuses}")
    repository = AlertRepository(session)
    alert = repository.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = body.status
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return _alert_to_out(alert)

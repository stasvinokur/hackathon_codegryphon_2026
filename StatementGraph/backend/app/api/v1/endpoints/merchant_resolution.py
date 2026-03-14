from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.schemas.statement import StatementActionResponse
from app.services.statement_workflow import StatementWorkflowService

router = APIRouter()


@router.post("/rebuild", response_model=StatementActionResponse)
def rebuild_merchant_resolution(session: Session = Depends(get_db_session)) -> StatementActionResponse:
    """Rebuild merchant normalization across all stored transactions."""

    service = StatementWorkflowService(session)
    updated = service.rebuild_merchant_resolution()
    return StatementActionResponse(
        statement_id="00000000-0000-0000-0000-000000000000",
        status="merchant-resolution-rebuilt",
        details={"updated_transactions": updated},
    )

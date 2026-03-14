from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.schemas.statement import (
    StatementActionResponse,
    StatementOut,
    StatementSummaryResponse,
    StatementUploadResponse,
)
from app.models.alert import Alert
from app.models.transaction import Transaction
from app.services.llm_analysis import generate_statement_analysis
from app.services.statement_workflow import StatementWorkflowService

router = APIRouter()


@router.delete("/all", status_code=204)
def clear_all_data(session: Session = Depends(get_db_session)) -> Response:
    """Remove all statements, transactions and alerts."""
    service = StatementWorkflowService(session)
    service.clear_all_data()
    return Response(status_code=204)


@router.post("/upload-pdf", response_model=StatementUploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
) -> StatementUploadResponse:
    service = StatementWorkflowService(session)
    try:
        statement = await service.upload_statement(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StatementUploadResponse(statement=StatementOut.model_validate(statement))


@router.post("/{statement_id}/parse", response_model=StatementActionResponse)
def parse_statement(statement_id: UUID, session: Session = Depends(get_db_session)) -> StatementActionResponse:
    service = StatementWorkflowService(session)
    try:
        rows = service.parse_statement(statement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    statement = service._require_statement(statement_id)
    return StatementActionResponse(
        statement_id=statement_id,
        status="parsed",
        details={"rows": rows},
        statement=StatementOut.model_validate(statement),
    )


@router.post("/{statement_id}/normalize", response_model=StatementActionResponse)
def normalize_statement(
    statement_id: UUID,
    session: Session = Depends(get_db_session),
) -> StatementActionResponse:
    service = StatementWorkflowService(session)
    try:
        rows = service.normalize_statement(statement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StatementActionResponse(
        statement_id=statement_id,
        status="normalized",
        details={"rows": rows},
    )


@router.post("/{statement_id}/score", response_model=StatementActionResponse)
def score_statement(statement_id: UUID, session: Session = Depends(get_db_session)) -> StatementActionResponse:
    service = StatementWorkflowService(session)
    try:
        alerts = service.score_statement(statement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StatementActionResponse(
        statement_id=statement_id,
        status="scored",
        details={"alerts": alerts},
    )


@router.get("/{statement_id}/summary", response_model=StatementSummaryResponse)
def summary_statement(
    statement_id: UUID,
    session: Session = Depends(get_db_session),
) -> StatementSummaryResponse:
    service = StatementWorkflowService(session)
    try:
        return service.build_summary(statement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{statement_id}/ai-analysis")
def ai_analysis(
    statement_id: UUID,
    session: Session = Depends(get_db_session),
) -> dict[str, str]:
    service = StatementWorkflowService(session)
    try:
        summary = service.build_summary(statement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    alerts = (
        session.query(Alert)
        .join(Transaction, Alert.transaction_id == Transaction.id)
        .filter(Transaction.statement_id == statement_id)
        .all()
    )
    try:
        text = generate_statement_analysis(summary, alerts)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc
    return {"analysis": text}

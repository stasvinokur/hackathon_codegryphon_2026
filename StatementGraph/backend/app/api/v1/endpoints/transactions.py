from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.transaction import TransactionListResponse, TransactionOut

router = APIRouter()


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    statement_id: UUID | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> TransactionListResponse:
    repository = TransactionRepository(session)
    items = repository.list(statement_id=statement_id)
    return TransactionListResponse(items=[TransactionOut.model_validate(item) for item in items], total=len(items))


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: UUID, session: Session = Depends(get_db_session)) -> TransactionOut:
    repository = TransactionRepository(session)
    transaction = repository.get(transaction_id)
    if transaction is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionOut.model_validate(transaction)

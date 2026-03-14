from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction


class TransactionRepository:
    """Persistence operations for transaction entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, transaction_id: UUID) -> Transaction | None:
        return self._session.get(Transaction, transaction_id)

    def list(self, statement_id: UUID | None = None) -> list[Transaction]:
        query: Select[tuple[Transaction]] = select(Transaction).order_by(Transaction.posted_at.desc())
        if statement_id is not None:
            query = query.where(Transaction.statement_id == statement_id)
        return list(self._session.scalars(query))

    def replace_for_statement(self, statement_id: UUID, items: list[Transaction]) -> list[Transaction]:
        self._session.query(Transaction).filter(Transaction.statement_id == statement_id).delete()
        self._session.add_all(items)
        self._session.commit()
        for item in items:
            self._session.refresh(item)
        return items

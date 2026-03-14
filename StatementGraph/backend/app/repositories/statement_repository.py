from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.statement import Statement


class StatementRepository:
    """Persistence operations for statement entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, statement: Statement) -> Statement:
        self._session.add(statement)
        self._session.commit()
        self._session.refresh(statement)
        return statement

    def get(self, statement_id: UUID) -> Statement | None:
        return self._session.get(Statement, statement_id)

    def list_all(self) -> list[Statement]:
        query = select(Statement).order_by(Statement.uploaded_at.desc())
        return list(self._session.scalars(query))

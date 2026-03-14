from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models.alert import Alert
from app.models.transaction import Transaction


class AlertRepository:
    """Persistence operations for alert entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_many(self, alerts: list[Alert]) -> list[Alert]:
        self._session.add_all(alerts)
        self._session.commit()
        for alert in alerts:
            self._session.refresh(alert)
        return alerts

    def replace_for_transaction_ids(self, transaction_ids: list[UUID], alerts: list[Alert]) -> list[Alert]:
        if transaction_ids:
            self._session.query(Alert).filter(Alert.transaction_id.in_(transaction_ids)).delete(
                synchronize_session=False
            )
        self._session.add_all(alerts)
        self._session.commit()
        for alert in alerts:
            self._session.refresh(alert)
        return alerts

    def get(self, alert_id: UUID) -> Alert | None:
        return self._session.get(Alert, alert_id)

    def list_by_statement(self, statement_id: UUID) -> list[Alert]:
        query: Select[tuple[Alert]] = (
            select(Alert)
            .join(Transaction, Alert.transaction_id == Transaction.id)
            .where(Transaction.statement_id == statement_id)
            .options(joinedload(Alert.transaction))
            .order_by(Alert.created_at.desc())
        )
        return list(self._session.scalars(query).unique())

    def list(self, severity: str | None = None) -> list[Alert]:
        query: Select[tuple[Alert]] = (
            select(Alert)
            .options(joinedload(Alert.transaction))
            .order_by(Alert.created_at.desc())
        )
        if severity:
            query = query.where(Alert.severity == severity)
        return list(self._session.scalars(query).unique())

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Transaction(Base):
    """Canonical card transaction record."""

    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    statement_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("statements.id"))

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    settlement_lag_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    amount_signed_original: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_original: Mapped[str] = mapped_column(String(16), default="RUB")
    currency_normalized: Mapped[str] = mapped_column(String(16), default="RUB")

    inflow_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    outflow_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    debt_after_transaction: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    description_raw: Mapped[str] = mapped_column(Text)
    description_clean: Mapped[str] = mapped_column(Text)
    merchant_raw: Mapped[str] = mapped_column(String(256))
    merchant_normalized: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    merchant_group: Mapped[str | None] = mapped_column(String(128), nullable=True)

    operation_type: Mapped[str] = mapped_column(String(64), default="debit")
    is_credit: Mapped[bool] = mapped_column(Boolean, default=False)
    is_refund_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_duplicate_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_burst_candidate: Mapped[bool] = mapped_column(Boolean, default=False)

    risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    anomaly_score: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    explanation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_row_json: Mapped[dict] = mapped_column(JSON, default=dict)

    statement: Mapped[Statement] = relationship(back_populates="transactions")
    alerts: Mapped[list[Alert]] = relationship(back_populates="transaction", cascade="all, delete-orphan")


from app.models.alert import Alert  # noqa: E402
from app.models.statement import Statement  # noqa: E402

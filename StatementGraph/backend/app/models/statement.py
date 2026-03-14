from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Statement(Base):
    """Card statement metadata extracted from uploaded files."""

    __tablename__ = "statements"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    bank_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    masked_card_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    statement_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    available_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    debt_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    minimum_payment: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grace_period_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(256), nullable=False)
    source_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="statement", cascade="all, delete-orphan"
    )


class Card(Base):
    """Card entity used by graph/export layers when card-level linkage is needed."""

    __tablename__ = "cards"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    masked_card_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    holder_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    statement_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("statements.id"), nullable=True)

    statement: Mapped[Statement | None] = relationship()


from app.models.transaction import Transaction  # noqa: E402

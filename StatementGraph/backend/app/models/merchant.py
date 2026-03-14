from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Merchant(Base):
    """Canonical merchant entity after normalization."""

    __tablename__ = "merchants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    normalized_name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    merchant_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    merchant_group: Mapped[str | None] = mapped_column(String(128), nullable=True)

    aliases: Mapped[list[MerchantAlias]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )


class MerchantAlias(Base):
    """Observed merchant alias linked to canonical merchant."""

    __tablename__ = "merchant_aliases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    merchant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("merchants.id"))
    merchant_alias: Mapped[str] = mapped_column(String(256), index=True)
    alias_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=1)

    merchant: Mapped[Merchant] = relationship(back_populates="aliases")

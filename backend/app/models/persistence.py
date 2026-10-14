"""Phase 4 persistence objects: currency registry, idempotency keys, snapshots.

Money columns here use :class:`app.db_types.ScaledMoneyType` — services see
exact ``Decimal`` values while SQLite stores scaled INTEGERs (×10 000).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db_types import ScaledMoneyType
from .base import Base


class Currency(Base):
    """Supported-currency registry (seeded idempotently)."""

    __tablename__ = "currencies"
    __table_args__ = (
        CheckConstraint("is_base IN (0,1)", name="is_base"),
        CheckConstraint("is_active IN (0,1)", name="is_active"),
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_base: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class IdempotencyKey(Base):
    """API mutation idempotency — atomic claim + persisted response (Phase 4 §9)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (Index("ix_idempotency_keys_expires", "expires_at"),)

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)


class AccountBalanceSnapshot(Base):
    """Monthly per-account rollup for expensive reports (Phase 4 §8)."""

    __tablename__ = "account_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "period_start", "period_end", name="uq_account_balance_snapshots_period"
        ),
        Index("ix_account_balance_snapshots_period", "period_end"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # FK enforced in DDL migration
    period_start: Mapped[str] = mapped_column(Text, nullable=False)
    period_end: Mapped[str] = mapped_column(Text, nullable=False)
    ending_debit: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    ending_credit: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    net_balance: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[str] = mapped_column(Text, nullable=False)

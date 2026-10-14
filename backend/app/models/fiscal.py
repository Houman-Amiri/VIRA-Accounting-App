"""Fiscal periods and the append-only audit trail."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"
    __table_args__ = (
        CheckConstraint("is_closed IN (0,1)", name="is_closed"),
        Index("ix_fiscal_periods_range", "start_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(Text, nullable=False)
    is_closed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    """Append-only audit records.  SQLite triggers reject UPDATE/DELETE."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("action IN ('INSERT','UPDATE','DELETE')", name="action"),
        Index("ix_audit_logs_record", "table_name", "record_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)

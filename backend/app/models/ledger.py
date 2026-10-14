"""Core double-entry ledger tables: accounts, journal_entries, transaction_splits.

All DDL is created STRICT (see Alembic migration 0001).  Row-level CHECK
constraints enforce the split invariant (exactly one side positive).  Posting
invariants (≥2 splits, Σ debits = Σ credits) are validated atomically by the
ledger service; SQLite triggers are a secondary guard for immutability.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

ACCOUNT_TYPES = ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")
NORMAL_BALANCES = ("DEBIT", "CREDIT")
ENTRY_STATUSES = ("DRAFT", "POSTED", "VOIDED")
RECONCILIATION_STATUSES = ("UNRECONCILED", "CLEARED", "RECONCILED")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('ASSET','LIABILITY','EQUITY','INCOME','EXPENSE')",
            name="account_type",
        ),
        CheckConstraint("normal_balance IN ('DEBIT','CREDIT')", name="normal_balance"),
        CheckConstraint("is_placeholder IN (0,1)", name="is_placeholder"),
        CheckConstraint("is_active IN (0,1)", name="is_active"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    normal_balance: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    is_placeholder: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    children: Mapped[list[Account]] = relationship(
        "Account", back_populates="parent", viewonly=True
    )
    parent: Mapped[Account | None] = relationship(
        "Account", back_populates="children", remote_side=[id]
    )


class JournalEntry(Base, TimestampMixin):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT','POSTED','VOIDED')", name="status"),
        Index("ix_journal_entries_date", "transaction_date", "entry_number"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    entry_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    transaction_date: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD
    posted_at: Mapped[str] = mapped_column(Text, nullable=False)
    payee: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    reversed_entry_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True
    )
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    splits: Mapped[list[TransactionSplit]] = relationship(
        "TransactionSplit",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        order_by="TransactionSplit.id",
    )


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"
    __table_args__ = (
        CheckConstraint(
            "debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0) "
            "AND (debit > 0 OR credit > 0)",
            name="one_side_positive",
        ),
        CheckConstraint(
            "functional_debit >= 0 AND functional_credit >= 0 "
            "AND NOT (functional_debit > 0 AND functional_credit > 0)",
            name="functional_one_side",
        ),
        CheckConstraint(
            "reconciliation_status IN ('UNRECONCILED','CLEARED','RECONCILED')",
            name="reconciliation_status",
        ),
        Index("ix_transaction_splits_account", "account_id", "journal_entry_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    journal_entry_id: Mapped[str] = mapped_column(
        Text, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        Text, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    reconciliation_session_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("reconciliation_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    debit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    exchange_rate: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100_000_000
    )
    functional_debit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    functional_credit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reconciliation_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="UNRECONCILED"
    )

    journal_entry: Mapped[JournalEntry] = relationship("JournalEntry", back_populates="splits")
    account: Mapped[Account] = relationship("Account")

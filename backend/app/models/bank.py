"""Bank statement import batches and raw statement lines (idempotent)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

FILE_FORMATS = ("CSV", "XLSX", "OFX", "QFX", "MT940", "CAMT053")
LINE_STATUSES = ("UNMATCHED", "SUGGESTED", "MATCHED", "IGNORED")


class BankImportBatch(Base):
    __tablename__ = "bank_import_batches"
    __table_args__ = (
        CheckConstraint(
            "file_format IN ('CSV','XLSX','OFX','QFX','MT940','CAMT053')",
            name="file_format",
        ),
        CheckConstraint("status IN ('IMPORTED','REVERTED')", name="status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    source_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="IMPORTED")
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    lines: Mapped[list[BankStatementLine]] = relationship(
        "BankStatementLine", back_populates="batch"
    )


class BankStatementLine(Base):
    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        CheckConstraint("status IN ('UNMATCHED','SUGGESTED','MATCHED','IGNORED')", name="status"),
        UniqueConstraint("account_id", "external_fitid", name="account_fitid"),
        UniqueConstraint("account_id", "dedup_hash", name="account_dedup"),
        Index("ix_bank_statement_lines_batch", "batch_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        Text, ForeignKey("bank_import_batches.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    external_fitid: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedup_hash: Mapped[str] = mapped_column(Text, nullable=False)
    value_date: Mapped[str] = mapped_column(Text, nullable=False)
    booking_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    payee_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # scaled 1e4, signed
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    category_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="UNMATCHED")

    batch: Mapped[BankImportBatch] = relationship("BankImportBatch", back_populates="lines")

"""Platform tables: users (auth), recurring entries (scheduler), documents."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

ROLES = ("OWNER", "BOOKKEEPER", "AUDITOR", "INGEST_API")
OCR_STATUSES = ("NONE", "PENDING", "DONE", "FAILED")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('OWNER','BOOKKEEPER','AUDITOR','INGEST_API')", name="role"
        ),
        CheckConstraint("is_active IN (0,1)", name="is_active"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="OWNER")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class RecurringEntry(Base):
    __tablename__ = "recurring_entries"
    __table_args__ = (CheckConstraint("is_active IN (0,1)", name="is_active"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expr: Mapped[str] = mapped_column(Text, nullable=False)  # 5-field cron
    template_json: Mapped[str] = mapped_column(Text, nullable=False)  # JE draft template
    next_run_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_entry_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("sha256", name="documents_sha256"),
        CheckConstraint("ocr_status IN ('NONE','PENDING','DONE','FAILED')", name="ocr_status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    journal_entry_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("journal_entries.id", ondelete="RESTRICT"), nullable=True
    )
    ocr_status: Mapped[str] = mapped_column(Text, nullable=False, default="NONE")
    ocr_data_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[str] = mapped_column(Text, nullable=False)

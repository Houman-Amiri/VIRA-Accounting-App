"""Phase 5 security objects: recovery codes, API keys, envelope credentials,
webhook dedup, and the append-only security audit trail."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MfaRecoveryCode(Base):
    """Single-use backup codes — only Argon2id hashes are stored (Phase 5 §1)."""

    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (Index("ix_mfa_recovery_codes_user", "user_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)  # FK in DDL
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class ApiKey(Base):
    """ingest_api scoped key — hashed secret, prefix for identification."""

    __tablename__ = "api_keys"
    __table_args__ = (
        CheckConstraint("role IN ('INGEST_API')", name="role"),
        UniqueConstraint("key_prefix", name="key_prefix"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="INGEST_API")
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class ExternalCredential(Base):
    """Envelope-encrypted third-party secret (bank/FX/LLM/webhook)."""

    __tablename__ = "external_credentials"
    __table_args__ = (UniqueConstraint("provider", "label", name="provider_label"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class WebhookEvent(Base):
    """HMAC-verified webhook dedup — event_id unique per provider."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        CheckConstraint("signature_ok IN (0,1)", name="signature_ok"),
        UniqueConstraint("provider", "event_id", name="event"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    signature_ok: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[str] = mapped_column(Text, nullable=False)
    payload_digest: Mapped[str] = mapped_column(Text, nullable=False)


class SecurityAuditLog(Base):
    """Append-only security events — triggers reject UPDATE/DELETE."""

    __tablename__ = "security_audit_logs"
    __table_args__ = (Index("ix_security_audit_logs_event", "event", "created_at"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

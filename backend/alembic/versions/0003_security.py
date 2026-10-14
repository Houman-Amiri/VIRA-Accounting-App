"""security hardening — recovery codes, API keys, envelope credentials, webhooks, security audit

Revision ID: 0003_security
Revises: 0002_persistence
Create Date: 2026-10-14

Phase 5 (Integration, Auth & Security) additions, all SQLite-compatible STRICT
tables with deterministic ck_/uq_/ix_ naming:

* ``mfa_recovery_codes`` — 10 single-use Argon2id-hashed backup codes per user
* ``api_keys`` — ingest_api scoped keys (hashed secret, shown once)
* ``external_credentials`` — envelope-encrypted third-party secrets (bank/FX/LLM)
* ``webhook_events`` — HMAC-verified webhook dedup (event_id unique)
* ``security_audit_logs`` — append-only security events (IP, user-agent, actor);
  SQLite triggers reject UPDATE/DELETE like ``audit_logs``
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_security"
down_revision: str | None = "0002_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGERS = ["trg_security_audit_no_update", "trg_security_audit_no_delete"]


def upgrade() -> None:
    conn = op.get_bind()
    stmts = [
        """
        CREATE TABLE mfa_recovery_codes (
            id TEXT NOT NULL PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX ix_mfa_recovery_codes_user ON mfa_recovery_codes(user_id)",
        """
        CREATE TABLE api_keys (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'INGEST_API',
            created_by TEXT REFERENCES users(id) ON DELETE RESTRICT,
            last_used_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_api_keys_role CHECK (role IN ('INGEST_API'))
        ) STRICT
        """,
        "CREATE UNIQUE INDEX uq_api_keys_prefix ON api_keys(key_prefix)",
        """
        CREATE TABLE external_credentials (
            id TEXT NOT NULL PRIMARY KEY,
            provider TEXT NOT NULL,
            label TEXT NOT NULL,
            ciphertext TEXT NOT NULL,
            key_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_external_credentials_label UNIQUE (provider, label)
        ) STRICT
        """,
        """
        CREATE TABLE webhook_events (
            id TEXT NOT NULL PRIMARY KEY,
            provider TEXT NOT NULL,
            event_id TEXT NOT NULL,
            signature_ok INTEGER NOT NULL,
            received_at TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            CONSTRAINT ck_webhook_events_signature_ok CHECK (signature_ok IN (0,1)),
            CONSTRAINT uq_webhook_events_event UNIQUE (provider, event_id)
        ) STRICT
        """,
        """
        CREATE TABLE security_audit_logs (
            id TEXT NOT NULL PRIMARY KEY,
            event TEXT NOT NULL,
            actor_id TEXT,
            ip TEXT,
            user_agent TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX ix_security_audit_logs_event ON security_audit_logs(event, created_at)",
        "CREATE TRIGGER trg_security_audit_no_update BEFORE UPDATE ON security_audit_logs\n"
        "BEGIN SELECT RAISE(ABORT, 'security audit logs are immutable'); END",
        "CREATE TRIGGER trg_security_audit_no_delete BEFORE DELETE ON security_audit_logs\n"
        "BEGIN SELECT RAISE(ABORT, 'security audit logs are immutable'); END",
    ]
    for stmt in stmts:
        conn.execute(sa.text(stmt))


def downgrade() -> None:
    conn = op.get_bind()
    for trg in TRIGGERS:
        conn.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg}"))
    for table in (
        "security_audit_logs",
        "webhook_events",
        "external_credentials",
        "api_keys",
        "mfa_recovery_codes",
    ):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))

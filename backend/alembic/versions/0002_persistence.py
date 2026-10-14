"""persistence hardening — idempotency, reconciliation sessions, snapshots, search

Revision ID: 0002_persistence
Revises: 0001_initial
Create Date: 2026-10-14

Phase 4 (Database & Persistence Layer) additions, all SQLite-compatible:
* ``currencies`` registry (seeded supported currencies)
* ``reconciliation_sessions`` + ``transaction_splits.reconciliation_session_id``
* ``idempotency_keys`` (atomic claim/replay for API mutations)
* ``account_balance_snapshots`` (monthly rollups for expensive reports)
* keyset-pagination index ``ix_journal_entries_date_id (transaction_date DESC, id DESC)``
* rollup view ``v_account_balances`` (POSTED splits only)
* FTS5 ``search_fts`` + sync triggers when the SQLite build supports FTS5
  (falls back to LIKE search at the service layer otherwise)
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_persistence"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FTS_TRIGGERS = [
    "trg_je_fts_insert",
    "trg_je_fts_update",
    "trg_je_fts_delete",
    "trg_accounts_fts_insert",
    "trg_accounts_fts_update",
    "trg_accounts_fts_delete",
]


def upgrade() -> None:
    conn = op.get_bind()
    stmts = [
        """
        CREATE TABLE currencies (
            code TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            is_base INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT ck_currencies_is_base CHECK (is_base IN (0,1)),
            CONSTRAINT ck_currencies_is_active CHECK (is_active IN (0,1))
        ) STRICT
        """,
        """
        CREATE TABLE reconciliation_sessions (
            id TEXT NOT NULL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            statement_date TEXT NOT NULL,
            beginning_balance INTEGER NOT NULL,
            ending_balance INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            completed_at TEXT,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_reconciliation_sessions_status
                CHECK (status IN ('OPEN','COMPLETED','ABANDONED'))
        ) STRICT
        """,
        "CREATE INDEX ix_reconciliation_sessions_account ON reconciliation_sessions(account_id, statement_date)",
        "ALTER TABLE transaction_splits ADD COLUMN reconciliation_session_id TEXT "
        "REFERENCES reconciliation_sessions(id) ON DELETE SET NULL",
        "CREATE INDEX ix_transaction_splits_session ON transaction_splits(reconciliation_session_id)",
        """
        CREATE TABLE idempotency_keys (
            key TEXT NOT NULL PRIMARY KEY,
            request_hash TEXT NOT NULL,
            response_status INTEGER,
            response_body TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX ix_idempotency_keys_expires ON idempotency_keys(expires_at)",
        """
        CREATE TABLE account_balance_snapshots (
            id TEXT NOT NULL PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            ending_debit INTEGER NOT NULL,
            ending_credit INTEGER NOT NULL,
            net_balance INTEGER NOT NULL,
            currency TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            CONSTRAINT uq_account_balance_snapshots_period
                UNIQUE (account_id, period_start, period_end)
        ) STRICT
        """,
        "CREATE INDEX ix_account_balance_snapshots_period ON account_balance_snapshots(period_end)",
        # Keyset/cursor pagination index (Phase 4 §8).
        "CREATE INDEX ix_journal_entries_date_id ON journal_entries(transaction_date DESC, id DESC)",
        # Rollup view over POSTED splits only (Phase 4 §8).
        """
        CREATE VIEW v_account_balances AS
        SELECT
            s.account_id AS account_id,
            a.code AS code,
            a.name AS name,
            a.account_type AS account_type,
            a.normal_balance AS normal_balance,
            COALESCE(SUM(s.debit), 0) AS debit,
            COALESCE(SUM(s.credit), 0) AS credit,
            COALESCE(SUM(s.debit - s.credit), 0) AS net_debit_balance,
            COALESCE(SUM(s.functional_debit), 0) AS functional_debit,
            COALESCE(SUM(s.functional_credit), 0) AS functional_credit
        FROM transaction_splits s
        JOIN journal_entries je ON je.id = s.journal_entry_id AND je.status = 'POSTED'
        JOIN accounts a ON a.id = s.account_id
        GROUP BY s.account_id
        """,
    ]
    for stmt in stmts:
        conn.execute(sa.text(stmt))

    # ---------- FTS5 search index (optional capability) ----------
    try:
        conn.execute(
            sa.text(
                "CREATE VIRTUAL TABLE search_fts USING fts5("
                "entity UNINDEXED, ref_id UNINDEXED, title, body, "
                "tokenize='unicode61')"
            )
        )
    except sa.exc.OperationalError:
        # SQLite build without FTS5 — service layer keeps a tested LIKE fallback.
        return

    fts_stmts = [
        """
        CREATE TRIGGER trg_je_fts_insert AFTER INSERT ON journal_entries
        BEGIN
            INSERT INTO search_fts(entity, ref_id, title, body)
            VALUES ('entry', NEW.id, NEW.description,
                    NEW.description || ' ' || COALESCE(NEW.payee, '') || ' #' || NEW.entry_number);
        END
        """,
        """
        CREATE TRIGGER trg_je_fts_update AFTER UPDATE ON journal_entries
        BEGIN
            DELETE FROM search_fts WHERE entity = 'entry' AND ref_id = OLD.id;
            INSERT INTO search_fts(entity, ref_id, title, body)
            VALUES ('entry', NEW.id, NEW.description,
                    NEW.description || ' ' || COALESCE(NEW.payee, '') || ' #' || NEW.entry_number);
        END
        """,
        """
        CREATE TRIGGER trg_je_fts_delete AFTER DELETE ON journal_entries
        BEGIN
            DELETE FROM search_fts WHERE entity = 'entry' AND ref_id = OLD.id;
        END
        """,
        """
        CREATE TRIGGER trg_accounts_fts_insert AFTER INSERT ON accounts
        BEGIN
            INSERT INTO search_fts(entity, ref_id, title, body)
            VALUES ('account', NEW.id, NEW.code || ' ' || NEW.name, NEW.name || ' ' || NEW.code);
        END
        """,
        """
        CREATE TRIGGER trg_accounts_fts_update AFTER UPDATE ON accounts
        BEGIN
            DELETE FROM search_fts WHERE entity = 'account' AND ref_id = OLD.id;
            INSERT INTO search_fts(entity, ref_id, title, body)
            VALUES ('account', NEW.id, NEW.code || ' ' || NEW.name, NEW.name || ' ' || NEW.code);
        END
        """,
        """
        CREATE TRIGGER trg_accounts_fts_delete AFTER DELETE ON accounts
        BEGIN
            DELETE FROM search_fts WHERE entity = 'account' AND ref_id = OLD.id;
        END
        """,
    ]
    for stmt in fts_stmts:
        conn.execute(sa.text(stmt))

    # Backfill existing rows into the FTS index.
    conn.execute(
        sa.text(
            "INSERT INTO search_fts(entity, ref_id, title, body) "
            "SELECT 'entry', id, description, "
            "description || ' ' || COALESCE(payee, '') || ' #' || entry_number "
            "FROM journal_entries"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO search_fts(entity, ref_id, title, body) "
            "SELECT 'account', id, code || ' ' || name, name || ' ' || code FROM accounts"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    for trg in FTS_TRIGGERS:
        conn.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg}"))
    conn.execute(sa.text("DROP TABLE IF EXISTS search_fts"))
    conn.execute(sa.text("DROP VIEW IF EXISTS v_account_balances"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_journal_entries_date_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS account_balance_snapshots"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_idempotency_keys_expires"))
    conn.execute(sa.text("DROP TABLE IF EXISTS idempotency_keys"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_transaction_splits_session"))
    conn.execute(
        sa.text(
            "ALTER TABLE transaction_splits DROP COLUMN reconciliation_session_id"
        )
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_reconciliation_sessions_account"))
    conn.execute(sa.text("DROP TABLE IF EXISTS reconciliation_sessions"))
    conn.execute(sa.text("DROP TABLE IF EXISTS currencies"))

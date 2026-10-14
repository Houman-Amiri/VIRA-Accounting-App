"""initial schema — STRICT tables, ledger CHECKs, immutability triggers

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-14

Raw SQLite DDL is used so every table is STRICT and every CHECK/trigger is
SQLite-compatible (no deferrable constraints).  Downgrade drops everything.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "users",
    "documents",
    "recurring_entries",
    "bank_statement_lines",
    "bank_import_batches",
    "exchange_rates",
    "audit_logs",
    "fiscal_periods",
    "transaction_splits",
    "journal_entries",
    "accounts",
]

TRIGGERS = [
    "trg_audit_logs_no_update",
    "trg_audit_logs_no_delete",
    "trg_je_protect_locked_delete",
    "trg_je_protect_posted_update",
    "trg_je_fiscal_lock_insert",
    "trg_je_fiscal_lock_update",
    "trg_split_protect_delete",
    "trg_split_protect_update",
]


def upgrade() -> None:
    conn = op.get_bind()
    stmts = [
        # ---------- core ledger ----------
        """
        CREATE TABLE accounts (
            id TEXT NOT NULL PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            normal_balance TEXT NOT NULL,
            currency TEXT NOT NULL,
            parent_id TEXT REFERENCES accounts(id) ON DELETE RESTRICT,
            path TEXT NOT NULL,
            is_placeholder INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            version_id INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT ck_accounts_account_type
                CHECK (account_type IN ('ASSET','LIABILITY','EQUITY','INCOME','EXPENSE')),
            CONSTRAINT ck_accounts_normal_balance
                CHECK (normal_balance IN ('DEBIT','CREDIT')),
            CONSTRAINT ck_accounts_is_placeholder CHECK (is_placeholder IN (0,1)),
            CONSTRAINT ck_accounts_is_active CHECK (is_active IN (0,1))
        ) STRICT
        """,
        "CREATE UNIQUE INDEX uq_accounts_code ON accounts(code)",
        "CREATE INDEX ix_accounts_parent_id ON accounts(parent_id)",
        "CREATE INDEX ix_accounts_path ON accounts(path)",
        """
        CREATE TABLE journal_entries (
            id TEXT NOT NULL PRIMARY KEY,
            entry_number INTEGER NOT NULL,
            transaction_date TEXT NOT NULL,
            posted_at TEXT NOT NULL,
            payee TEXT,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            reversed_entry_id TEXT REFERENCES journal_entries(id) ON DELETE RESTRICT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            version_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT ck_journal_entries_status
                CHECK (status IN ('DRAFT','POSTED','VOIDED'))
        ) STRICT
        """,
        "CREATE UNIQUE INDEX uq_journal_entries_entry_number ON journal_entries(entry_number)",
        "CREATE INDEX ix_journal_entries_date ON journal_entries(transaction_date, entry_number)",
        """
        CREATE TABLE transaction_splits (
            id TEXT NOT NULL PRIMARY KEY,
            journal_entry_id TEXT NOT NULL REFERENCES journal_entries(id) ON DELETE RESTRICT,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            memo TEXT,
            debit INTEGER NOT NULL DEFAULT 0,
            credit INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL,
            exchange_rate INTEGER NOT NULL DEFAULT 100000000,
            functional_debit INTEGER NOT NULL DEFAULT 0,
            functional_credit INTEGER NOT NULL DEFAULT 0,
            reconciliation_status TEXT NOT NULL DEFAULT 'UNRECONCILED',
            CONSTRAINT ck_transaction_splits_one_side_positive
                CHECK (debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0)
                       AND (debit > 0 OR credit > 0)),
            CONSTRAINT ck_transaction_splits_functional_one_side
                CHECK (functional_debit >= 0 AND functional_credit >= 0
                       AND NOT (functional_debit > 0 AND functional_credit > 0)),
            CONSTRAINT ck_transaction_splits_reconciliation_status
                CHECK (reconciliation_status IN ('UNRECONCILED','CLEARED','RECONCILED'))
        ) STRICT
        """,
        "CREATE INDEX ix_transaction_splits_account ON transaction_splits(account_id, journal_entry_id)",
        "CREATE INDEX ix_transaction_splits_entry ON transaction_splits(journal_entry_id)",
        # ---------- fiscal + audit ----------
        """
        CREATE TABLE fiscal_periods (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_closed INTEGER NOT NULL DEFAULT 0,
            closed_at TEXT,
            CONSTRAINT ck_fiscal_periods_is_closed CHECK (is_closed IN (0,1))
        ) STRICT
        """,
        "CREATE INDEX ix_fiscal_periods_range ON fiscal_periods(start_date, end_date)",
        """
        CREATE TABLE audit_logs (
            id TEXT NOT NULL PRIMARY KEY,
            table_name TEXT NOT NULL,
            record_id TEXT NOT NULL,
            action TEXT NOT NULL,
            old_data TEXT,
            new_data TEXT,
            changed_at TEXT NOT NULL,
            actor_id TEXT,
            CONSTRAINT ck_audit_logs_action CHECK (action IN ('INSERT','UPDATE','DELETE'))
        ) STRICT
        """,
        "CREATE INDEX ix_audit_logs_record ON audit_logs(table_name, record_id)",
        # ---------- fx ----------
        """
        CREATE TABLE exchange_rates (
            id TEXT NOT NULL PRIMARY KEY,
            base_currency TEXT NOT NULL,
            quote_currency TEXT NOT NULL,
            rate_date TEXT NOT NULL,
            rate INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'frankfurter',
            CONSTRAINT uq_exchange_rates_rate_pair_date
                UNIQUE (base_currency, quote_currency, rate_date)
        ) STRICT
        """,
        "CREATE INDEX ix_exchange_rates_date ON exchange_rates(rate_date)",
        # ---------- bank import ----------
        """
        CREATE TABLE bank_import_batches (
            id TEXT NOT NULL PRIMARY KEY,
            account_id TEXT REFERENCES accounts(id) ON DELETE RESTRICT,
            source_filename TEXT NOT NULL,
            file_format TEXT NOT NULL,
            file_sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'IMPORTED',
            line_count INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT ck_bank_import_batches_file_format
                CHECK (file_format IN ('CSV','XLSX','OFX','QFX','MT940','CAMT053')),
            CONSTRAINT ck_bank_import_batches_status
                CHECK (status IN ('IMPORTED','REVERTED'))
        ) STRICT
        """,
        """
        CREATE TABLE bank_statement_lines (
            id TEXT NOT NULL PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES bank_import_batches(id) ON DELETE RESTRICT,
            account_id TEXT REFERENCES accounts(id) ON DELETE RESTRICT,
            external_fitid TEXT,
            dedup_hash TEXT NOT NULL,
            value_date TEXT NOT NULL,
            booking_date TEXT,
            payee_raw TEXT,
            description_raw TEXT,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            category_suggestion TEXT,
            status TEXT NOT NULL DEFAULT 'UNMATCHED',
            CONSTRAINT ck_bank_statement_lines_status
                CHECK (status IN ('UNMATCHED','SUGGESTED','MATCHED','IGNORED')),
            CONSTRAINT uq_bank_statement_lines_account_fitid UNIQUE (account_id, external_fitid),
            CONSTRAINT uq_bank_statement_lines_account_dedup UNIQUE (account_id, dedup_hash)
        ) STRICT
        """,
        "CREATE INDEX ix_bank_statement_lines_batch ON bank_statement_lines(batch_id)",
        # ---------- ops ----------
        """
        CREATE TABLE users (
            id TEXT NOT NULL PRIMARY KEY,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'OWNER',
            is_active INTEGER NOT NULL DEFAULT 1,
            totp_secret_enc TEXT,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_users_role
                CHECK (role IN ('OWNER','BOOKKEEPER','AUDITOR','INGEST_API')),
            CONSTRAINT ck_users_is_active CHECK (is_active IN (0,1))
        ) STRICT
        """,
        "CREATE UNIQUE INDEX uq_users_username ON users(username)",
        """
        CREATE TABLE recurring_entries (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            cron_expr TEXT NOT NULL,
            template_json TEXT NOT NULL,
            next_run_at TEXT,
            last_run_at TEXT,
            last_entry_id TEXT REFERENCES journal_entries(id) ON DELETE RESTRICT,
            is_active INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT ck_recurring_entries_is_active CHECK (is_active IN (0,1))
        ) STRICT
        """,
        """
        CREATE TABLE documents (
            id TEXT NOT NULL PRIMARY KEY,
            sha256 TEXT NOT NULL,
            media_type TEXT NOT NULL,
            original_name TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            storage_path TEXT NOT NULL,
            journal_entry_id TEXT REFERENCES journal_entries(id) ON DELETE RESTRICT,
            ocr_status TEXT NOT NULL DEFAULT 'NONE',
            ocr_data_json TEXT,
            uploaded_at TEXT NOT NULL,
            CONSTRAINT uq_documents_sha256 UNIQUE (sha256),
            CONSTRAINT ck_documents_ocr_status
                CHECK (ocr_status IN ('NONE','PENDING','DONE','FAILED'))
        ) STRICT
        """,
        # ---------- triggers: append-only audit ----------
        """
        CREATE TRIGGER trg_audit_logs_no_update BEFORE UPDATE ON audit_logs
        BEGIN
            SELECT RAISE(ABORT, 'audit_logs are immutable');
        END
        """,
        """
        CREATE TRIGGER trg_audit_logs_no_delete BEFORE DELETE ON audit_logs
        BEGIN
            SELECT RAISE(ABORT, 'audit_logs are immutable');
        END
        """,
        # ---------- triggers: posted/voided entries immutable ----------
        """
        CREATE TRIGGER trg_je_protect_locked_delete BEFORE DELETE ON journal_entries
        BEGIN
            SELECT RAISE(ABORT, 'posted journal entries cannot be deleted')
            WHERE OLD.status IN ('POSTED', 'VOIDED');
        END
        """,
        """
        CREATE TRIGGER trg_je_protect_posted_update BEFORE UPDATE ON journal_entries
        BEGIN
            SELECT RAISE(ABORT, 'posted journal entries cannot change date/number')
            WHERE OLD.status = 'POSTED'
              AND (NEW.transaction_date <> OLD.transaction_date
                   OR NEW.entry_number <> OLD.entry_number);
        END
        """,
        # ---------- triggers: closed fiscal periods reject writes ----------
        """
        CREATE TRIGGER trg_je_fiscal_lock_insert BEFORE INSERT ON journal_entries
        BEGIN
            SELECT RAISE(ABORT, 'fiscal period is closed')
            WHERE EXISTS (SELECT 1 FROM fiscal_periods fp
                          WHERE fp.is_closed = 1
                            AND NEW.transaction_date BETWEEN fp.start_date AND fp.end_date);
        END
        """,
        """
        CREATE TRIGGER trg_je_fiscal_lock_update BEFORE UPDATE OF transaction_date ON journal_entries
        BEGIN
            SELECT RAISE(ABORT, 'fiscal period is closed')
            WHERE EXISTS (SELECT 1 FROM fiscal_periods fp
                          WHERE fp.is_closed = 1
                            AND NEW.transaction_date BETWEEN fp.start_date AND fp.end_date);
        END
        """,
        # ---------- triggers: splits of posted entries immutable ----------
        """
        CREATE TRIGGER trg_split_protect_delete BEFORE DELETE ON transaction_splits
        BEGIN
            SELECT RAISE(ABORT, 'splits of posted entries cannot be deleted')
            WHERE (SELECT status FROM journal_entries WHERE id = OLD.journal_entry_id)
                  IN ('POSTED', 'VOIDED');
        END
        """,
        """
        CREATE TRIGGER trg_split_protect_update BEFORE UPDATE ON transaction_splits
        BEGIN
            SELECT RAISE(ABORT, 'splits of posted entries cannot change amounts/accounts')
            WHERE (SELECT status FROM journal_entries WHERE id = OLD.journal_entry_id) = 'POSTED'
              AND (NEW.debit <> OLD.debit OR NEW.credit <> OLD.credit
                   OR NEW.account_id <> OLD.account_id
                   OR NEW.functional_debit <> OLD.functional_debit
                   OR NEW.functional_credit <> OLD.functional_credit);
        END
        """,
    ]
    for stmt in stmts:
        conn.exec_driver_sql(stmt)


def downgrade() -> None:
    conn = op.get_bind()
    for trg in TRIGGERS:
        conn.exec_driver_sql(f"DROP TRIGGER IF EXISTS {trg}")
    for table in reversed(TABLES):
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")

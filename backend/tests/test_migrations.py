"""Alembic migration upgrade AND downgrade paths against temp SQLite files."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from tests.conftest import downgrade_migrations, run_migrations


def test_upgrade_downgrade_cycle(db_path) -> None:
    run_migrations()
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        assert {"accounts", "journal_entries", "transaction_splits", "audit_logs"} <= tables
        # STRICT tables actually strict?
        sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE name='transaction_splits'")
        ).scalar()
        assert "STRICT" in sql.upper()
        # triggers exist
        triggers = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            ).fetchall()
        }
        assert "trg_audit_logs_no_delete" in triggers
        assert "trg_je_protect_locked_delete" in triggers
    engine.dispose()

    downgrade_migrations()
    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        assert "accounts" not in tables
    engine.dispose()

    # re-upgrade works (fresh cycle)
    run_migrations()

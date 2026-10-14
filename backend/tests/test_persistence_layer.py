"""Phase 4 persistence-layer contract: STRICT DDL, CHECKs, FKs, views, decorators.

Runs raw SQL against the migrated on-disk database to prove the actual SQLite
constraints fire (not just ORM validation).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.db_types import ScaledFxRateType, ScaledMoneyType
from app.ids import utc_now_iso
from app.money import from_scaled, to_scaled

# ---------------- TypeDecorators (Phase 4 §1) ----------------


def test_scaled_money_type_roundtrip() -> None:
    t = ScaledMoneyType()
    bound = t.process_bind_param(Decimal("12.3456"), None)
    assert bound == 123_456
    assert t.process_result_value(bound, None) == Decimal("12.3456")
    assert t.process_bind_param(None, None) is None
    with pytest.raises(TypeError):
        t.process_bind_param(1.5, None)  # float is forbidden


def test_scaled_fx_type_roundtrip() -> None:
    t = ScaledFxRateType()
    bound = t.process_bind_param(Decimal("72000.5"), None)
    assert bound == 7_200_050_000_000
    assert t.process_result_value(bound, None) == Decimal("72000.5")


def test_scaled_money_type_overflow_guard() -> None:
    from app.money import MoneyError

    t = ScaledMoneyType()
    with pytest.raises(MoneyError):
        t.process_bind_param(Decimal("1e14"), None)  # at MAX_ABS_AMOUNT bound


# ---------------- schema objects from migration 0002 ----------------


def _raw_conn(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def test_0002_objects_exist(database, db_path) -> None:
    conn = _raw_conn(db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"currencies", "reconciliation_sessions", "idempotency_keys",
                "account_balance_snapshots"} <= tables
        views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
        assert "v_account_balances" in views
        idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "ix_journal_entries_date_id" in idx
    finally:
        conn.close()


def test_stored_amounts_are_integers(database, db_path, session) -> None:
    """Money columns persist scaled INTEGERs — never REAL."""
    session.execute(
        text(
            "INSERT INTO accounts (id, code, name, account_type, normal_balance, currency,"
            " parent_id, path, is_placeholder, is_active, version_id)"
            " VALUES ('a-1','9901','x','ASSET','DEBIT','IRR',NULL,'9901',0,1,1)"
        )
    )
    session.execute(
        text(
            "INSERT INTO journal_entries (id, entry_number, transaction_date, posted_at,"
            " payee, description, status, reversed_entry_id, metadata_json, version_id,"
            " created_at, updated_at)"
            " VALUES ('j-1', 9001, '2026-01-01', '2026-01-01T00:00:00', NULL, 't',"
            " 'POSTED', NULL, '{}', 1, '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
    )
    session.execute(
        text(
            "INSERT INTO transaction_splits (id, journal_entry_id, account_id, memo,"
            " debit, credit, currency, exchange_rate, functional_debit, functional_credit,"
            " reconciliation_status)"
            " VALUES ('s-1','j-1','a-1',NULL, 123456, 0, 'IRR', 100000000, 123456, 0,"
            " 'UNRECONCILED')"
        )
    )
    session.commit()
    conn = _raw_conn(db_path)
    try:
        typ, val = conn.execute(
            "SELECT typeof(debit), debit FROM transaction_splits WHERE id='s-1'"
        ).fetchone()
        assert typ == "integer"
        assert val == to_scaled(Decimal("12.3456"))
    finally:
        conn.close()


# ---------------- row-level CHECK constraints fire in SQLite ----------------


def _insert_account_raw(conn: sqlite3.Connection, code: str) -> None:
    conn.execute(
        "INSERT INTO accounts (id, code, name, account_type, normal_balance, currency,"
        " parent_id, path, is_placeholder, is_active, version_id)"
        f" VALUES ('{code}','{code}','n','ASSET','DEBIT','IRR',NULL,'{code}',0,1,1)"
    )


def _insert_entry_raw(conn: sqlite3.Connection, entry_id: str) -> None:
    conn.execute(
        "INSERT INTO journal_entries (id, entry_number, transaction_date, posted_at,"
        " payee, description, status, reversed_entry_id, metadata_json, version_id,"
        " created_at, updated_at)"
        f" VALUES ('{entry_id}', abs(random()) % 1000000, '2026-01-01',"
        " '2026-01-01T00:00:00', NULL, 't', 'POSTED', NULL, '{}', 1,"
        " '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )


def _insert_split_raw(
    conn: sqlite3.Connection, split_id: str, entry_id: str, account: str,
    debit: int, credit: int,
) -> None:
    conn.execute(
        "INSERT INTO transaction_splits (id, journal_entry_id, account_id, memo,"
        " debit, credit, currency, exchange_rate, functional_debit, functional_credit,"
        " reconciliation_status)"
        f" VALUES ('{split_id}','{entry_id}','{account}',NULL, {debit}, {credit},"
        f" 'IRR', 100000000, {debit}, {credit}, 'UNRECONCILED')"
    )


def test_split_check_rejects_double_sided_and_empty(database, db_path) -> None:
    conn = _raw_conn(db_path)
    try:
        _insert_account_raw(conn, "8801")
        _insert_entry_raw(conn, "e-ck1")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_split_raw(conn, "s-bad1", "e-ck1", "8801", 10, 10)  # both sides
        with pytest.raises(sqlite3.IntegrityError):
            _insert_split_raw(conn, "s-bad2", "e-ck1", "8801", 0, 0)  # empty
        with pytest.raises(sqlite3.IntegrityError):
            _insert_split_raw(conn, "s-bad3", "e-ck1", "8801", -5, 0)  # negative
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_fk_enforced_delete_restrict(database, db_path) -> None:
    conn = _raw_conn(db_path)
    try:
        _insert_account_raw(conn, "8802")
        _insert_entry_raw(conn, "e-fk1")
        _insert_split_raw(conn, "s-fk1", "e-fk1", "8802", 10000, 0)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM accounts WHERE code='8802'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM journal_entries WHERE id='e-fk1'")
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_audit_log_immutable_triggers(database, db_path) -> None:
    conn = _raw_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_logs (id, table_name, record_id, action, old_data,"
            f" new_data, changed_at, actor_id) VALUES ('au-1','accounts','x','INSERT',"
            f" NULL, '{{}}', '{utc_now_iso()}', NULL)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE audit_logs SET action='DELETE' WHERE id='au-1'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM audit_logs WHERE id='au-1'")
        conn.execute("ROLLBACK")
    finally:
        conn.close()


# ---------------- rollup view reconciles with splits ----------------


def test_view_reconciles_with_posted_splits(database, session) -> None:
    session.execute(
        text(
            "INSERT INTO accounts (id, code, name, account_type, normal_balance, currency,"
            " parent_id, path, is_placeholder, is_active, version_id)"
            " VALUES ('av-1','8810','view acc','ASSET','DEBIT','IRR',NULL,'8810',0,1,1)"
        )
    )
    session.execute(
        text(
            "INSERT INTO journal_entries (id, entry_number, transaction_date, posted_at,"
            " payee, description, status, reversed_entry_id, metadata_json, version_id,"
            " created_at, updated_at)"
            " VALUES ('jv-1', 9100, '2026-02-01', '2026-02-01T00:00:00', NULL, 'v',"
            " 'POSTED', NULL, '{}', 1, '2026-02-01T00:00:00', '2026-02-01T00:00:00')"
        )
    )
    session.execute(
        text(
            "INSERT INTO transaction_splits (id, journal_entry_id, account_id, memo,"
            " debit, credit, currency, exchange_rate, functional_debit, functional_credit,"
            " reconciliation_status)"
            " VALUES ('sv-1','jv-1','av-1',NULL, 420001, 0, 'IRR', 100000000, 420001, 0,"
            " 'UNRECONCILED')"
        )
    )
    session.commit()
    row = session.execute(
        text("SELECT debit, credit, net_debit_balance FROM v_account_balances WHERE account_id='av-1'")
    ).one()
    assert from_scaled(int(row[0])) == Decimal("42.0001")
    assert int(row[1]) == 0
    assert int(row[2]) == 420001


def test_snapshots_reconcile_with_view(database, session) -> None:
    from app.services.snapshots import compute_snapshots

    session.execute(
        text(
            "INSERT INTO accounts (id, code, name, account_type, normal_balance, currency,"
            " parent_id, path, is_placeholder, is_active, version_id)"
            " VALUES ('av-2','8811','snap acc','ASSET','DEBIT','IRR',NULL,'8811',0,1,1)"
        )
    )
    session.execute(
        text(
            "INSERT INTO journal_entries (id, entry_number, transaction_date, posted_at,"
            " payee, description, status, reversed_entry_id, metadata_json, version_id,"
            " created_at, updated_at)"
            " VALUES ('jv-2', 9101, '2026-02-15', '2026-02-15T00:00:00', NULL, 'v2',"
            " 'POSTED', NULL, '{}', 1, '2026-02-15T00:00:00', '2026-02-15T00:00:00')"
        )
    )
    session.execute(
        text(
            "INSERT INTO transaction_splits (id, journal_entry_id, account_id, memo,"
            " debit, credit, currency, exchange_rate, functional_debit, functional_credit,"
            " reconciliation_status)"
            " VALUES ('sv-2','jv-2','av-2',NULL, 100000, 0, 'IRR', 100000000, 100000, 0,"
            " 'UNRECONCILED')"
        )
    )
    session.commit()

    snaps = compute_snapshots(session, period_start="2026-02-01", period_end="2026-02-28")
    by_account = {s.account_id: s for s in snaps}
    assert "av-2" in by_account
    assert by_account["av-2"].net_balance == Decimal("10.0000")

    view_net = session.execute(
        text("SELECT net_debit_balance FROM v_account_balances WHERE account_id='av-2'")
    ).scalar()
    assert int(view_net) == to_scaled(by_account["av-2"].net_balance)

    # idempotent rebuild
    snaps2 = compute_snapshots(session, period_start="2026-02-01", period_end="2026-02-28")
    assert len([s for s in snaps2 if s.account_id == "av-2"]) == 1

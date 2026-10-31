"""0005 -> actual catalog DDL: exact preservation, FK safety and atomic failure."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, event

from alembic import command
from app.config import load_settings
from app.db import Database
from app.schemas.ledger import AccountCreate, JournalEntryCreate, SplitCreate
from app.seed import seed_currencies
from app.services.ledger import LedgerService


def cfg():
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return config


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            name: sorted(db.execute(f'SELECT * FROM "{name}"').fetchall(), key=repr)
            for name in tables
        }


def baseline(path):
    command.upgrade(cfg(), "0005_pricing_settings")
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        now = "2026-10-17T00:00:00Z"
        db.execute(
            "INSERT INTO suppliers(id,name,created_at,updated_at) VALUES ('s','فروشنده قدیمی',?,?)",
            (now, now),
        )
        for ident, kind, unit in [("f", "FILAMENT", "G"), ("p", "PRODUCT", "PCS")]:
            db.execute(
                "INSERT INTO inventory_items(id,name,kind,unit,quantity,min_quantity,unit_price,supplier_id,created_at,updated_at) VALUES (?,?,?,?,123456,10001,70001,'s',?,?)",
                (ident, "قدیمی " + ident, kind, unit, now, now),
            )
            db.execute(
                "INSERT INTO stock_movements(id,item_id,kind,quantity,occurred_at,created_at) VALUES (?,?,'IN',123456,?,?)",
                ("m" + ident, ident, now, now),
            )
        db.execute(
            "INSERT INTO orders(id,order_number,order_date,customer_name,created_at,updated_at) VALUES ('o',1,'2026-10-17','قدیمی',?,?)",
            (now, now),
        )
        db.execute(
            "INSERT INTO order_items(id,order_id,product_name,inventory_item_id) VALUES ('l','o','محصول','p')"
        )
        db.execute(
            "INSERT INTO production_jobs(id,job_number,order_id,order_item_id,product_name,filament_item_id,product_item_id,created_at,updated_at) VALUES ('j',1,'o','l','محصول','f','p',?,?)",
            (now, now),
        )
    # Genuine posted, balanced ledger with scaled-four precision; never rewritten.
    database = Database(load_settings())
    try:
        with database.session() as session:
            seed_currencies(session)
            service = LedgerService(session)
            a = service.create_account(
                AccountCreate(code="1010", name="صندوق", account_type="ASSET")
            )
            b = service.create_account(
                AccountCreate(code="3010", name="سرمایه", account_type="EQUITY")
            )
            entry = service.create_draft(
                JournalEntryCreate(
                    transaction_date="2026-10-17",
                    description="مانده قدیمی",
                    splits=[
                        SplitCreate(account_id=a.id, debit="123456.7891"),
                        SplitCreate(account_id=b.id, credit="123456.7891"),
                    ],
                )
            )
            service.post(entry.id)
    finally:
        database.dispose()


def test_catalog_migration_preserves_every_old_row_and_references(db_path):
    baseline(db_path)
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("CREATE INDEX local_inventory_price ON inventory_items(unit_price)")
        db.execute(
            "CREATE TRIGGER local_inventory_guard BEFORE UPDATE OF name ON inventory_items WHEN NEW.name='blocked' BEGIN SELECT RAISE(ABORT,'local inventory rule'); END"
        )
    before = dump(db_path)
    command.upgrade(cfg(), "head")
    after = dump(db_path)
    assert set(after) - set(before) == {
        "item_types",
        "item_units",
        "production_job_filaments",
    }
    for table, rows in before.items():
        if table != "alembic_version":
            assert after[table] == rows, table
    with closing(sqlite3.connect(db_path)) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute(
            "SELECT SUM(functional_debit),SUM(functional_credit) FROM transaction_splits"
        ).fetchone() == (1234567891, 1234567891)
        assert (
            "STRICT"
            in db.execute("SELECT sql FROM sqlite_master WHERE name='inventory_items'").fetchone()[
                0
            ]
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('local_inventory_price','local_inventory_guard')"
            ).fetchone()[0]
            == 2
        )
        with pytest.raises(sqlite3.IntegrityError, match="local inventory rule"):
            db.execute("UPDATE inventory_items SET name='blocked' WHERE id='f'")
        db.rollback()
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE inventory_items SET kind='missing' WHERE id='f'")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM suppliers WHERE id='s'")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM stock_movements")
    command.upgrade(cfg(), "head")
    assert dump(db_path) == after  # re-entry is a no-op


def test_catalog_failure_rolls_back_ddl_rows_and_revision_together(db_path):
    baseline(db_path)
    before = dump(db_path)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("ALTER TABLE inventory_items_rebuild"):
            raise RuntimeError("injected failure after copying and dropping old physical table")

    event.listen(Engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            command.upgrade(cfg(), "head")
    finally:
        event.remove(Engine, "before_cursor_execute", fail)
    assert dump(db_path) == before
    with closing(sqlite3.connect(db_path)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    command.upgrade(cfg(), "head")  # retry the same failed migration succeeds


def test_catalog_downgrade_refuses_to_discard_custom_choices(db_path):
    command.upgrade(cfg(), "head")
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("INSERT INTO item_units VALUES ('custom','لیتر',1,1,'now','now')")
    before = dump(db_path)
    with pytest.raises(RuntimeError, match="Refusing lossy"):
        command.downgrade(cfg(), "0005_pricing_settings")
    assert dump(db_path) == before

"""Persisted item types/units; preserve all operations and scaled integer values.

SQLite cannot remove a CHECK in place. Rebuild only inventory_items inside the
migration runner's explicit IMMEDIATE transaction, with FK verification before
commit. No parent rename (which could rewrite child FK targets), no CASCADE,
no quantity conversions, no rewriting stock/history/ledger tables.
"""

from __future__ import annotations

from alembic import op

revision = "0006_item_catalog"
down_revision = "0005_pricing_settings"
branch_labels = None
depends_on = None

COLUMNS = "id,name,kind,color,unit,quantity,min_quantity,unit_price,supplier_id,purchased_at,notes,is_active,version_id,created_at,updated_at"


def rebuild(*, legacy: bool) -> None:
    conn = op.get_bind()
    if conn.exec_driver_sql("PRAGMA foreign_keys").scalar() != 0:
        raise RuntimeError("catalog migration requires the atomic FK-checked migration runner")
    kind = (
        "TEXT NOT NULL DEFAULT 'FILAMENT' CHECK(kind IN ('FILAMENT','PRODUCT'))"
        if legacy
        else "TEXT NOT NULL DEFAULT 'FILAMENT' REFERENCES item_types(id) ON DELETE RESTRICT"
    )
    unit = (
        "TEXT NOT NULL DEFAULT 'G' CHECK(unit IN ('G','PCS'))"
        if legacy
        else "TEXT NOT NULL DEFAULT 'G' REFERENCES item_units(id) ON DELETE RESTRICT"
    )
    supplier_delete = "SET NULL" if legacy else "RESTRICT"
    conn.exec_driver_sql(f"""CREATE TABLE inventory_items_rebuild (
        id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, kind {kind}, color TEXT,
        unit {unit}, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),
        min_quantity INTEGER NOT NULL DEFAULT 0 CHECK(min_quantity>=0),
        unit_price INTEGER NOT NULL DEFAULT 0 CHECK(unit_price>=0),
        supplier_id TEXT REFERENCES suppliers(id) ON DELETE {supplier_delete},
        purchased_at TEXT, notes TEXT, is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
        version_id INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    ) STRICT""")
    conn.exec_driver_sql(
        f"INSERT INTO inventory_items_rebuild ({COLUMNS}) SELECT {COLUMNS} FROM inventory_items"
    )
    for a, b in [
        ("inventory_items", "inventory_items_rebuild"),
        ("inventory_items_rebuild", "inventory_items"),
    ]:
        if conn.exec_driver_sql(
            f"SELECT {COLUMNS} FROM {a} EXCEPT SELECT {COLUMNS} FROM {b}"
        ).fetchone():
            raise RuntimeError("catalog migration copy did not preserve exact inventory rows")
    conn.exec_driver_sql("DROP TABLE inventory_items")
    conn.exec_driver_sql("ALTER TABLE inventory_items_rebuild RENAME TO inventory_items")
    conn.exec_driver_sql("CREATE INDEX ix_inventory_items_kind ON inventory_items(kind,is_active)")
    conn.exec_driver_sql("CREATE INDEX ix_inventory_items_supplier ON inventory_items(supplier_id)")


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("""CREATE TABLE item_units (
        id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
        version_id INTEGER NOT NULL DEFAULT 1 CHECK(version_id>0),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    ) STRICT""")
    conn.exec_driver_sql("""CREATE TABLE item_types (
        id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL UNIQUE,
        required_unit TEXT REFERENCES item_units(id) ON DELETE RESTRICT,
        production_role TEXT NOT NULL DEFAULT 'NONE' CHECK(production_role IN ('NONE','FILAMENT','PRODUCT')),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
        version_id INTEGER NOT NULL DEFAULT 1 CHECK(version_id>0),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    ) STRICT""")
    now = "2026-10-17T00:00:00Z"
    conn.exec_driver_sql(
        "INSERT INTO item_units VALUES ('G','گرم',1,1,?,?), ('PCS','عدد',1,1,?,?)",
        (now, now, now, now),
    )
    conn.exec_driver_sql(
        "INSERT INTO item_types VALUES ('FILAMENT','فیلامنت','G','FILAMENT',1,1,?,?), ('PRODUCT','محصول','PCS','PRODUCT',1,1,?,?)",
        (now, now, now, now),
    )
    rebuild(legacy=False)


def downgrade() -> None:
    conn = op.get_bind()
    if conn.exec_driver_sql(
        "SELECT 1 FROM item_types WHERE id NOT IN ('FILAMENT','PRODUCT') OR is_active<>1 OR version_id<>1 UNION ALL SELECT 1 FROM item_units WHERE id NOT IN ('G','PCS') OR is_active<>1 OR version_id<>1"
    ).fetchone():
        raise RuntimeError(
            "Refusing lossy catalog downgrade; restore a verified pre-upgrade database snapshot instead"
        )
    rebuild(legacy=True)
    conn.exec_driver_sql("DROP TABLE item_types")
    conn.exec_driver_sql("DROP TABLE item_units")

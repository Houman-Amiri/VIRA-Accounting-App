"""operations domain — warehouse, suppliers, orders, production (MASTER_PROMPT §3)

Revision ID: 0004_operations
Revises: 0003_security
Create Date: 2026-10-15

Adds the 3D-printing business core the product vision mandates:

* ``suppliers`` — price/quality/delivery scores for supplier suggestion
* ``inventory_items`` — filament spools and produced models (quantity,
  unit price, minimum quantity → stockout alarm)
* ``stock_movements`` — append-only stock ledger (IN/OUT/ADJUST); UPDATE and
  DELETE are rejected by triggers like ``audit_logs``
* ``orders`` / ``order_items`` — customer orders with line details
* ``production_jobs`` — a run that consumes filament and yields products

All tables are STRICT with non-negative CHECKs on amounts; quantities and money
are scaled INTEGERs (×10 000) as everywhere else.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_operations"
down_revision: str | None = "0003_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRIGGERS = ("trg_stock_movements_no_update", "trg_stock_movements_no_delete")


def upgrade() -> None:
    conn = op.get_bind()
    stmts = [
        """
        CREATE TABLE suppliers (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            score_price INTEGER NOT NULL DEFAULT 50,
            score_quality INTEGER NOT NULL DEFAULT 50,
            score_delivery INTEGER NOT NULL DEFAULT 50,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            version_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_suppliers_name UNIQUE (name),
            CONSTRAINT ck_suppliers_is_active CHECK (is_active IN (0,1)),
            CONSTRAINT ck_suppliers_score_price CHECK (score_price BETWEEN 0 AND 100),
            CONSTRAINT ck_suppliers_score_quality CHECK (score_quality BETWEEN 0 AND 100),
            CONSTRAINT ck_suppliers_score_delivery CHECK (score_delivery BETWEEN 0 AND 100)
        ) STRICT
        """,
        "CREATE INDEX ix_suppliers_name ON suppliers(name)",
        """
        CREATE TABLE inventory_items (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'FILAMENT',
            color TEXT,
            unit TEXT NOT NULL DEFAULT 'G',
            quantity INTEGER NOT NULL DEFAULT 0,
            min_quantity INTEGER NOT NULL DEFAULT 0,
            unit_price INTEGER NOT NULL DEFAULT 0,
            supplier_id TEXT REFERENCES suppliers(id) ON DELETE SET NULL,
            purchased_at TEXT,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            version_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT ck_inventory_items_kind CHECK (kind IN ('FILAMENT','PRODUCT')),
            CONSTRAINT ck_inventory_items_unit CHECK (unit IN ('G','PCS')),
            CONSTRAINT ck_inventory_items_is_active CHECK (is_active IN (0,1)),
            CONSTRAINT ck_inventory_items_quantity_non_negative CHECK (quantity >= 0),
            CONSTRAINT ck_inventory_items_min_quantity_non_negative CHECK (min_quantity >= 0),
            CONSTRAINT ck_inventory_items_unit_price_non_negative CHECK (unit_price >= 0)
        ) STRICT
        """,
        "CREATE INDEX ix_inventory_items_kind ON inventory_items(kind, is_active)",
        "CREATE INDEX ix_inventory_items_supplier ON inventory_items(supplier_id)",
        """
        CREATE TABLE stock_movements (
            id TEXT NOT NULL PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
            kind TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_cost INTEGER,
            reason TEXT,
            reference_id TEXT,
            note TEXT,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_stock_movements_kind CHECK (kind IN ('IN','OUT','ADJUST')),
            CONSTRAINT ck_stock_movements_quantity_non_negative CHECK (quantity >= 0)
        ) STRICT
        """,
        "CREATE INDEX ix_stock_movements_item ON stock_movements(item_id, occurred_at)",
        "CREATE TRIGGER trg_stock_movements_no_update BEFORE UPDATE ON stock_movements\n"
        "BEGIN SELECT RAISE(ABORT, 'stock movements are append-only'); END",
        "CREATE TRIGGER trg_stock_movements_no_delete BEFORE DELETE ON stock_movements\n"
        "BEGIN SELECT RAISE(ABORT, 'stock movements are append-only'); END",
        """
        CREATE TABLE orders (
            id TEXT NOT NULL PRIMARY KEY,
            order_number INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            customer_phone TEXT,
            customer_address TEXT,
            status TEXT NOT NULL DEFAULT 'NEW',
            channel TEXT NOT NULL DEFAULT 'direct',
            notes TEXT,
            version_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_orders_number UNIQUE (order_number),
            CONSTRAINT ck_orders_status CHECK (status IN ('NEW','CONFIRMED','IN_PRODUCTION',
                'READY','SHIPPED','DELIVERED','CANCELLED')),
            CONSTRAINT ck_orders_channel CHECK (channel IN ('direct','marketplace'))
        ) STRICT
        """,
        "CREATE INDEX ix_orders_status ON orders(status, order_date)",
        "CREATE INDEX ix_orders_customer ON orders(customer_name)",
        """
        CREATE TABLE order_items (
            id TEXT NOT NULL PRIMARY KEY,
            order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            product_name TEXT NOT NULL,
            variant TEXT NOT NULL DEFAULT 'plain',
            quantity INTEGER NOT NULL DEFAULT 10000,
            unit_price INTEGER NOT NULL DEFAULT 0,
            unit_cost INTEGER NOT NULL DEFAULT 0,
            weight_g INTEGER NOT NULL DEFAULT 0,
            print_hours INTEGER NOT NULL DEFAULT 0,
            inventory_item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
            notes TEXT,
            CONSTRAINT ck_order_items_variant CHECK (variant IN ('plain','chain')),
            CONSTRAINT ck_order_items_quantity_positive CHECK (quantity > 0),
            CONSTRAINT ck_order_items_unit_price_non_negative CHECK (unit_price >= 0),
            CONSTRAINT ck_order_items_unit_cost_non_negative CHECK (unit_cost >= 0),
            CONSTRAINT ck_order_items_weight_non_negative CHECK (weight_g >= 0),
            CONSTRAINT ck_order_items_hours_non_negative CHECK (print_hours >= 0)
        ) STRICT
        """,
        "CREATE INDEX ix_order_items_order ON order_items(order_id)",
        """
        CREATE TABLE production_jobs (
            id TEXT NOT NULL PRIMARY KEY,
            job_number INTEGER NOT NULL,
            order_id TEXT REFERENCES orders(id) ON DELETE SET NULL,
            order_item_id TEXT REFERENCES order_items(id) ON DELETE SET NULL,
            product_name TEXT NOT NULL,
            variant TEXT NOT NULL DEFAULT 'plain',
            channel TEXT NOT NULL DEFAULT 'direct',
            quantity INTEGER NOT NULL DEFAULT 10000,
            status TEXT NOT NULL DEFAULT 'PLANNED',
            filament_item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
            product_item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
            filament_grams INTEGER NOT NULL DEFAULT 0,
            print_hours INTEGER NOT NULL DEFAULT 0,
            unit_cost INTEGER NOT NULL DEFAULT 0,
            unit_price INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            started_at TEXT,
            finished_at TEXT,
            version_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_production_jobs_number UNIQUE (job_number),
            CONSTRAINT ck_production_jobs_status CHECK (status IN ('PLANNED','IN_PROGRESS',
                'DONE','CANCELLED')),
            CONSTRAINT ck_production_jobs_variant CHECK (variant IN ('plain','chain')),
            CONSTRAINT ck_production_jobs_channel CHECK (channel IN ('direct','marketplace')),
            CONSTRAINT ck_production_jobs_quantity_positive CHECK (quantity > 0),
            CONSTRAINT ck_production_jobs_filament_non_negative CHECK (filament_grams >= 0),
            CONSTRAINT ck_production_jobs_hours_non_negative CHECK (print_hours >= 0),
            CONSTRAINT ck_production_jobs_unit_cost_non_negative CHECK (unit_cost >= 0),
            CONSTRAINT ck_production_jobs_unit_price_non_negative CHECK (unit_price >= 0)
        ) STRICT
        """,
        "CREATE INDEX ix_production_jobs_status ON production_jobs(status, created_at)",
        "CREATE INDEX ix_production_jobs_order ON production_jobs(order_id)",
    ]
    for stmt in stmts:
        conn.execute(sa.text(stmt))


def downgrade() -> None:
    conn = op.get_bind()
    for trg in TRIGGERS:
        conn.execute(sa.text(f"DROP TRIGGER IF EXISTS {trg}"))
    for table in (
        "production_jobs",
        "order_items",
        "orders",
        "stock_movements",
        "inventory_items",
        "suppliers",
    ):
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))

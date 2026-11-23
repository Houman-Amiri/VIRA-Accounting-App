"""Order-line charges («هزینهٔ طراحی» and the owner's variables) + design rate.

The design rate is one of the owner's pricing variables: a flag on the row says
which one, so the orders page never has to guess by name. Each order line can
then carry its own charge rows — design hours × that rate, or a variable the
owner picked for the line — and the proforma prints them separately.

Everything is additive: existing orders, totals and prices are untouched, and a
line with no charges reads exactly as before.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_order_charges_design_rate"
down_revision: str | None = "0009_pricing_variables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        "ALTER TABLE pricing_variables "
        "ADD COLUMN is_design_rate INTEGER NOT NULL DEFAULT 0 "
        "CONSTRAINT ck_pricing_variable_design_rate CHECK (is_design_rate IN (0, 1))"
    )
    conn.exec_driver_sql(
        """
        CREATE TABLE order_item_charges (
            id TEXT NOT NULL PRIMARY KEY,
            order_item_id TEXT NOT NULL
                REFERENCES order_items(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            kind TEXT NOT NULL DEFAULT 'VARIABLE',
            variable_id TEXT
                REFERENCES pricing_variables(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            hours INTEGER NOT NULL DEFAULT 0,
            rate INTEGER NOT NULL DEFAULT 0,
            amount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_order_item_charge_kind
                CHECK (kind IN ('DESIGN', 'VARIABLE')),
            CONSTRAINT ck_order_item_charge_hours CHECK (hours >= 0),
            CONSTRAINT ck_order_item_charge_rate CHECK (rate >= 0),
            CONSTRAINT ck_order_item_charge_amount CHECK (amount >= 0),
            CONSTRAINT ck_order_item_charge_name CHECK (length(trim(name)) > 0)
        ) STRICT
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX ix_order_item_charges_item ON order_item_charges(order_item_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE order_item_charges")
    # SQLite dropped column support is fine for this additive flag.
    op.execute("ALTER TABLE pricing_variables DROP COLUMN is_design_rate")

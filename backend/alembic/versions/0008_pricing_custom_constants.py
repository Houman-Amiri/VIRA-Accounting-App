"""Owner-defined pricing constants (added next to the seven built-ins).

The built-in constants mirror `قیمت نهایی.xlsx` and must not change. This table
is additive: each row is a cost the owner adds to his own price, with the method
that says how it is calculated. Nothing here rewrites an existing price, an
order or a production job.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_pricing_custom_constants"
down_revision: str | None = "0007_production_filaments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHODS = "('PER_UNIT','PER_BATCH','PERCENT_OF_COST','PERCENT_OF_PRICE')"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        f"""
        CREATE TABLE pricing_custom_constants (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            method TEXT NOT NULL,
            value INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT ck_pricing_custom_method CHECK (method IN {METHODS}),
            CONSTRAINT ck_pricing_custom_value CHECK (value >= 0),
            CONSTRAINT ck_pricing_custom_active CHECK (is_active IN (0, 1)),
            CONSTRAINT ck_pricing_custom_name CHECK (length(trim(name)) > 0)
        ) STRICT
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX ix_pricing_custom_constants_order "
        "ON pricing_custom_constants(position, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE pricing_custom_constants")

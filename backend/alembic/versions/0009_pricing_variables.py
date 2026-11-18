"""Owner-defined pricing *variables* — values that change from job to job.

A constant (`pricing_custom_constants`) is a stored amount the owner sets once.
A variable is a named number the owner re-enters on the pricing page for the job
in front of him («نرخ دلار امروز»، «اجرت پرسنل»). Each variable says *how* it hits
the price:

* `PER_UNIT`  (جزیی)  — per piece;
* `PER_ORDER` (کلی)   — once on the whole order, either added to the total
  (`ONE_TIME`) or spread over the quantity (`SPLIT`).

Additive only: no existing price, order, job or document is touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_pricing_variables"
down_revision: str | None = "0008_pricing_custom_constants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        CREATE TABLE pricing_variables (
            id TEXT NOT NULL PRIMARY KEY,
            name TEXT NOT NULL,
            scope TEXT NOT NULL,
            basis TEXT NOT NULL,
            allocation TEXT NOT NULL,
            value INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT ck_pricing_variable_scope
                CHECK (scope IN ('PER_UNIT', 'PER_ORDER')),
            CONSTRAINT ck_pricing_variable_basis
                CHECK (basis IN ('AMOUNT', 'PERCENT_OF_COST', 'PERCENT_OF_PRICE')),
            CONSTRAINT ck_pricing_variable_allocation
                CHECK (allocation IN ('ONE_TIME', 'SPLIT')),
            CONSTRAINT ck_pricing_variable_value CHECK (value >= 0),
            CONSTRAINT ck_pricing_variable_active CHECK (is_active IN (0, 1)),
            CONSTRAINT ck_pricing_variable_name CHECK (length(trim(name)) > 0)
        ) STRICT
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX ix_pricing_variables_order ON pricing_variables(position, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE pricing_variables")

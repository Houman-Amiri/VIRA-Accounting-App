"""Add an order-level discount without changing existing orders."""
from collections.abc import Sequence
from alembic import op

revision: str = "0012_order_discount"
down_revision: str | None = "0011_order_variable_quantity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN discount_type TEXT NOT NULL DEFAULT 'AMOUNT' "
               "CONSTRAINT ck_order_discount_type CHECK (discount_type IN ('AMOUNT', 'PERCENT'))")
    op.execute("ALTER TABLE orders ADD COLUMN discount_value INTEGER NOT NULL DEFAULT 0 "
               "CONSTRAINT ck_order_discount_value CHECK (discount_value >= 0)")


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN discount_value")
    op.execute("ALTER TABLE orders DROP COLUMN discount_type")

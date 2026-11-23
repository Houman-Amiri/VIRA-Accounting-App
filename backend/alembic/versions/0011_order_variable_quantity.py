"""Snapshot the quantity of a pricing variable on an order charge.

NULL identifies old, directly-entered amounts and leaves them unchanged.
"""
from collections.abc import Sequence
from alembic import op

revision: str = "0011_order_variable_quantity"
down_revision: str | None = "0010_order_charges_design_rate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE order_item_charges ADD COLUMN quantity INTEGER "
               "CONSTRAINT ck_order_item_charge_quantity CHECK (quantity IS NULL OR quantity >= 0)")


def downgrade() -> None:
    op.execute("ALTER TABLE order_item_charges DROP COLUMN quantity")

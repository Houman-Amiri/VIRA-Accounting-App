"""Remember an order's pre-cancellation state; legacy cancelled rows stay NULL."""
from collections.abc import Sequence

from alembic import op

revision: str = "0013_order_cancel_restore"
down_revision: str | None = "0012_order_discount"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE orders ADD COLUMN status_before_cancel TEXT "
        "CONSTRAINT ck_order_status_before_cancel CHECK "
        "(status_before_cancel IS NULL OR status_before_cancel IN "
        "('NEW', 'CONFIRMED', 'IN_PRODUCTION', 'READY'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN status_before_cancel")

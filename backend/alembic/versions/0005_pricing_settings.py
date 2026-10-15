"""Shared pricing constants; no existing prices or operations are rewritten."""
from alembic import op

revision = "0005_pricing_settings"
down_revision = "0004_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pricing_settings (
            id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),
            filament_per_gram INTEGER NOT NULL CHECK (filament_per_gram >= 0),
            electricity_per_kwh INTEGER NOT NULL CHECK (electricity_per_kwh >= 0),
            depreciation_per_hour INTEGER NOT NULL CHECK (depreciation_per_hour >= 0),
            profit_factor INTEGER NOT NULL CHECK (profit_factor >= 0),
            chain_per_unit INTEGER NOT NULL CHECK (chain_per_unit >= 0),
            shipment_per_batch INTEGER NOT NULL CHECK (shipment_per_batch >= 0),
            label_per_unit INTEGER NOT NULL CHECK (label_per_unit >= 0),
            version_id INTEGER NOT NULL CHECK (version_id >= 1),
            updated_at TEXT NOT NULL
        ) STRICT
    """)
    # Six money values: Toman × 10 Rials × 10000. The multiplier is unitless × 10000.
    op.execute("""
        INSERT INTO pricing_settings VALUES
        (1, 300000000, 140000000, 1000000000, 25000, 800000000, 15000000000,
         800000000, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
    """)


def downgrade() -> None:
    op.execute("DROP TABLE pricing_settings")

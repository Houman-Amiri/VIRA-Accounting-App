"""Per-spool filament components of a production job.

Revision ID: 0007_production_filaments
Revises: 0006_item_catalog

A printed model is often built from several spools. ``production_jobs`` keeps
its legacy single-spool columns (``filament_item_id``/``filament_grams``) for
existing rows and for the list view; this child table records one row per spool
with its own grams-per-unit and price-per-gram snapshot so finishing can deduct
each spool and the UI can price each component.

Additive and STRICT: no table rebuild, no rewrite of existing production rows,
no change to any scaled INTEGER value.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_production_filaments"
down_revision: str | None = "0006_item_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        CREATE TABLE production_job_filaments (
            id TEXT NOT NULL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            filament_item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
            grams_per_unit INTEGER NOT NULL DEFAULT 0,
            unit_cost INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            CONSTRAINT ck_production_job_filaments_grams CHECK (grams_per_unit >= 0),
            CONSTRAINT ck_production_job_filaments_cost CHECK (unit_cost >= 0)
        ) STRICT
        """
    )
    conn.exec_driver_sql(
        "CREATE INDEX ix_production_job_filaments_job "
        "ON production_job_filaments(job_id, position)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("DROP INDEX IF EXISTS ix_production_job_filaments_job")
    conn.exec_driver_sql("DROP TABLE IF EXISTS production_job_filaments")

"""Alembic environment — SQLite-only migrations.

The database path is resolved from ``SQLITE_DATABASE_PATH`` (or the platform
default from :mod:`app.config`).  Migrations run with the same pragmas as the
application engine.  Import ``app.models`` so all tables are registered.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = load_settings()
config.set_main_option(
    "sqlalchemy.url", f"sqlite+pysqlite:///{settings.sqlite_database_path}"
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # SQLite table rebuilds must not cascade into referencing history. Only
        # this cold migrator connection disables FK enforcement, never app DB
        # sessions. Explicit BEGIN makes DDL, copied data AND revision atomic.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000")
        connection.commit()
        try:
            with connection.begin():
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("pre-migration foreign key violations; refusing changes")
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    render_as_batch=True,
                    transactional_ddl=True,
                )
                with context.begin_transaction():
                    context.run_migrations()
                if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("post-migration foreign key violations; rolling back")
                if connection.exec_driver_sql("PRAGMA integrity_check").scalar() != "ok":
                    raise RuntimeError("post-migration integrity check failed; rolling back")
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

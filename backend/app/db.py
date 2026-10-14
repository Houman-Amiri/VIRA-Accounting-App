"""SQLite engine/session management.

Enforced on every connection: ``PRAGMA foreign_keys=ON``,
``journal_mode=WAL``, ``synchronous=NORMAL``, ``busy_timeout=5000`` — verified
at startup.  Write transactions use ``BEGIN IMMEDIATE`` (SQLite has a single
writer; no advisory locks) with bounded retries on transient lock failures.
Sync SQLAlchemy sessions are used consistently (never mixed with async).
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings

log = logging.getLogger(__name__)

REQUIRED_PRAGMAS = {
    "foreign_keys": "1",
    "journal_mode": "wal",
    "synchronous": "1",  # NORMAL
}
BUSY_TIMEOUT_MS = 5000
LOCK_RETRY_ATTEMPTS = 5
LOCK_RETRY_SLEEP_S = 0.1


class DatabaseNotReady(RuntimeError):
    pass


def make_engine(settings: Settings, *, echo: bool = False) -> Engine:
    assert settings.sqlite_database_path is not None
    db_path = Path(settings.sqlite_database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(
        url,
        echo=echo,
        future=True,
        connect_args={"timeout": BUSY_TIMEOUT_MS / 1000, "check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn: sqlite3.Connection, _record: object) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        # disable pysqlite's implicit BEGIN so we control transaction mode
        dbapi_conn.isolation_level = None
        cur.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(conn: object) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")  # type: ignore[attr-defined]

    return engine


def verify_pragmas(engine: Engine) -> dict[str, str]:
    """Confirm required SQLite settings are active (called at startup)."""
    found: dict[str, str] = {}
    with engine.connect() as conn:
        for pragma in ("foreign_keys", "journal_mode", "synchronous", "busy_timeout"):
            row = conn.execute(text(f"PRAGMA {pragma}")).scalar()
            found[pragma] = str(row)
    if found.get("foreign_keys") != "1":
        raise DatabaseNotReady(f"foreign_keys not enabled: {found}")
    if found.get("journal_mode", "").lower() != "wal":
        raise DatabaseNotReady(f"journal_mode not WAL: {found}")
    if found.get("synchronous") not in {"1", "NORMAL", "normal"}:
        raise DatabaseNotReady(f"synchronous not NORMAL: {found}")
    if int(found.get("busy_timeout", "0")) < BUSY_TIMEOUT_MS:
        raise DatabaseNotReady(f"busy_timeout too low: {found}")
    ver = sqlite3.sqlite_version_info
    if ver < (3, 37, 0):
        raise DatabaseNotReady(f"SQLite {sqlite3.sqlite_version} too old for STRICT tables")
    if ver < (3, 45, 0):
        log.warning(
            "SQLite %s < 3.45 (production target); continuing (STRICT/FTS5 available)",
            sqlite3.sqlite_version,
        )
    return found


def check_invariants(engine: Engine) -> dict[str, object]:
    """Ledger + integrity invariants used by health checks and restore tests."""
    result: dict[str, object] = {}
    with engine.connect() as conn:
        result["integrity_check"] = conn.execute(text("PRAGMA integrity_check")).scalar()
        fk_rows = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        result["foreign_key_violations"] = len(fk_rows)
        row = conn.execute(
            text(
                "SELECT COALESCE(SUM(functional_debit),0), COALESCE(SUM(functional_credit),0) "
                "FROM transaction_splits"
            )
        ).one()
        result["total_debits"] = int(row[0])
        result["total_credits"] = int(row[1])
        result["balanced"] = int(row[0]) == int(row[1])
    return result


class Database:
    """Engine + session factory + retrying write helper."""

    def __init__(self, settings: Settings, *, echo: bool = False) -> None:
        self.settings = settings
        self.engine = make_engine(settings, echo=echo)
        self.session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def verify(self) -> dict[str, str]:
        return verify_pragmas(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional session — commits on success, rolls back on error."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def write_session(self, *, retries: int = LOCK_RETRY_ATTEMPTS) -> Iterator[Session]:
        """Write transaction (BEGIN IMMEDIATE) with bounded lock retries."""
        attempt = 0
        while True:
            try:
                with self.session() as session:
                    yield session
                return
            except sqlite3.OperationalError as exc:
                attempt += 1
                if "locked" not in str(exc).lower() or attempt > retries:
                    raise
                log.warning("database is locked; retry %s/%s", attempt, retries)
                time.sleep(LOCK_RETRY_SLEEP_S * attempt)

    def dispose(self) -> None:
        self.engine.dispose()

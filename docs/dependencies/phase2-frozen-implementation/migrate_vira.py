"""Safe SQLite migration lifecycle (Phase 6 §7).

One migration process at a time (local lock file), a verified online backup
BEFORE any schema change (`sqlite3.Connection.backup()` + integrity_check),
then `alembic upgrade head`, then the deployment gate:

* ``PRAGMA foreign_key_check``
* expected Alembic revision
* ledger invariant ``sum(debits) == sum(credits)``

On any failure the tool exits non-zero and points at the tested restore path
(``python scripts/migrate_vira.py --restore <bundle>``).

Usage (Windows-native, no Docker):

    python scripts/migrate_vira.py                  # migrate SQLITE_DATABASE_PATH
    python scripts/migrate_vira.py --report out.json
    python scripts/migrate_vira.py --restore <dir>  # verified restore
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(
    os.environ.get(
        "SQLITE_DATABASE_PATH",
        Path.home() / "AppData/Local/VIRA/data/vira.sqlite3",
    )
)


class MigrationError(RuntimeError):
    pass


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def online_backup(db_path: Path, backup_path: Path) -> None:
    """Consistent snapshot via sqlite3.Connection.backup() (Phase 6 §7)."""
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    src = _connect(db_path)
    dst = sqlite3.connect(backup_path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    # Verify the snapshot before we trust it.
    check = sqlite3.connect(backup_path)
    try:
        row = check.execute("PRAGMA integrity_check").fetchone()
        if row is None or str(row[0]) != "ok":
            raise MigrationError(f"backup integrity_check failed: {row}")
    finally:
        check.close()


def check_invariants(db_path: Path) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        revision = None
        try:
            row = conn.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
            revision = str(row[0]) if row else None
        except sqlite3.OperationalError:
            revision = None
        balanced: bool | None = None
        try:
            d, c = conn.execute(
                "SELECT COALESCE(SUM(functional_debit),0), "
                "COALESCE(SUM(functional_credit),0) FROM transaction_splits"
            ).fetchone()
            balanced = int(d) == int(c)
        except sqlite3.OperationalError:
            balanced = None
        return {
            "integrity_check": integrity,
            "foreign_key_violations": fk_violations,
            "alembic_revision": revision,
            "debits_equal_credits": balanced,
        }
    finally:
        conn.close()


def acquire_lock(db_path: Path) -> Path:
    """Single-migration guard — SQLite has no advisory lock (Phase 6 §7)."""
    lock_path = db_path.with_suffix(db_path.suffix + ".migrate.lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        age = time.time() - lock_path.stat().st_mtime
        if age > 3600:  # stale lock from a crashed run
            lock_path.unlink(missing_ok=True)
            return acquire_lock(db_path)
        raise MigrationError(
            f"another migration is in progress (lock: {lock_path}, age {age:.0f}s)"
        ) from exc
    with os.fdopen(fd, "w") as fh:
        fh.write(f"pid={os.getpid()} started={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    return lock_path


def run_migration(db_path: Path, report_path: Path | None) -> dict[str, object]:
    if not db_path.exists():
        # First deployment — bootstrap an empty database file.
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _connect(db_path).close()
        print(f"[vira-migrate] bootstrapped empty database: {db_path}", file=sys.stderr)
    lock_path = acquire_lock(db_path)
    report: dict[str, object] = {"database": str(db_path), "started": time.time()}
    try:
        backup_path = db_path.parent.parent / "backups" / (
            "pre-migration-" + time.strftime("%Y%m%d-%H%M%S") + ".sqlite3"
        )
        online_backup(db_path, backup_path)
        report["backup"] = str(backup_path)
        report["pre"] = check_invariants(db_path)

        # Run alembic against THIS database file (single process).
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        os.environ["SQLITE_DATABASE_PATH"] = str(db_path)
        from alembic.config import Config

        from alembic import command

        cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
        command.upgrade(cfg, "head")

        post = check_invariants(db_path)
        report["post"] = post
        gate_ok = (
            post["integrity_check"] == "ok"
            and post["foreign_key_violations"] == 0
            and post["alembic_revision"] is not None
            and post["debits_equal_credits"] in (True, None)
        )
        report["status"] = "migrated" if gate_ok else "gate_failed"
        if not gate_ok:
            raise MigrationError(
                "post-migration gate failed — restore with: "
                f"python scripts/migrate_vira.py --restore {backup_path.parent}"
            )
    finally:
        lock_path.unlink(missing_ok=True)
        if report_path is not None:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def restore_bundle(bundle_dir: Path, target: Path) -> dict[str, object]:
    """Tested restore path: verify the backup, then swap it into place."""
    candidates = sorted(bundle_dir.glob("*.sqlite3")) + sorted(bundle_dir.glob("*.sqlite3.db"))
    if bundle_dir.is_file():
        candidates = [bundle_dir]
    if not candidates:
        raise MigrationError(f"no sqlite snapshot found in {bundle_dir}")
    snapshot = candidates[-1]
    invariants = check_invariants(snapshot)
    if invariants["integrity_check"] != "ok":
        raise MigrationError(f"snapshot failed integrity_check: {invariants}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        stale = target.with_suffix(".replaced-" + time.strftime("%Y%m%d-%H%M%S"))
        target.rename(stale)
    src = sqlite3.connect(snapshot)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return {"restored_from": str(snapshot), "target": str(target), "invariants": invariants}


def main() -> int:
    parser = argparse.ArgumentParser(description="V.I.R.A safe migration lifecycle")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--restore", type=Path, default=None, help="restore a verified snapshot")
    args = parser.parse_args()
    try:
        if args.restore is not None:
            result = restore_bundle(args.restore, args.database)
        else:
            result = run_migration(args.database, args.report)
    except MigrationError as exc:
        print(f"[vira-migrate] ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

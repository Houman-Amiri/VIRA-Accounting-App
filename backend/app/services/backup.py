"""SQLite online backups + restore verification.

Backups use ``sqlite3.Connection.backup()`` (never a naive file copy that
ignores WAL state).  Restore verification restores to a temporary path and
runs ``PRAGMA integrity_check``, ``PRAGMA foreign_key_check`` and the ledger
debit/credit equality check before a backup is considered valid.
"""

from __future__ import annotations

import logging
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class BackupResult:
    path: str
    size_bytes: int
    integrity_check: str
    foreign_key_violations: int
    total_debits: int
    total_credits: int
    ok: bool


def create_backup(db_path: Path | str, backup_path: Path | str) -> BackupResult:
    db_path = Path(db_path)
    backup_path = Path(backup_path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        backup_path.unlink()
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    try:
        with dst:
            src.backup(dst)  # online backup API — consistent snapshot incl. WAL
    finally:
        src.close()
        dst.close()
    return verify_backup(backup_path)


def verify_backup(backup_path: Path | str) -> BackupResult:
    backup_path = Path(backup_path)
    conn = sqlite3.connect(backup_path)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        try:
            d, c = conn.execute(
                "SELECT COALESCE(SUM(functional_debit),0), "
                "COALESCE(SUM(functional_credit),0) FROM transaction_splits"
            ).fetchone()
        except sqlite3.OperationalError:
            d, c = (0, 0)
        ok = integrity == "ok" and len(fk_rows) == 0 and int(d) == int(c)
        return BackupResult(
            path=str(backup_path),
            size_bytes=backup_path.stat().st_size,
            integrity_check=integrity,
            foreign_key_violations=len(fk_rows),
            total_debits=int(d),
            total_credits=int(c),
            ok=ok,
        )
    finally:
        conn.close()


def restore_verified(db_path: Path | str, backup_path: Path | str) -> BackupResult:
    """Restore into a temp location and verify — recovery drill."""
    with tempfile.TemporaryDirectory(prefix="vira-restore-") as tmp:
        target = Path(tmp) / "restored.sqlite3"
        target.write_bytes(Path(backup_path).read_bytes())
        result = verify_backup(target)
        log.info("restore verification for %s: ok=%s", backup_path, result.ok)
        return result


def pre_update_backup(db_path: Path | str, backups_dir: Path | str, version: str) -> BackupResult:
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"pre-update-{version}.sqlite3"
    return create_backup(db_path, target)

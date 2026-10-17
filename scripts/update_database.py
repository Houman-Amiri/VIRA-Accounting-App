"""Updater-only cold DB rollback. stdlib only; shipped outside {app} in the delta.

Call snapshot AFTER stopping writers, restore AFTER stopping a failed target and
restoring the old interpreter. Never select a 'latest' backup: use this attempt's
verified snapshot. The failed database/WAL are retained, never silently erased.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)


def fingerprint(path: Path) -> str:
    with closing(read_only(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("SQLite foreign key check failed")
        revisions = db.execute("SELECT version_num FROM alembic_version").fetchall()
        if len(revisions) != 1 or not revisions[0][0]:
            raise ValueError("not a versioned application database")
        digest = hashlib.sha256()
        # SQL dump preserves SQL definitions, triggers, exact scaled INTEGERs,
        # IDs and all rows. Physical WAL/checkpoint counters are not user data.
        for statement in db.iterdump():
            digest.update(statement.encode("utf-8"))
            digest.update(b"\n")
        for pragma in ("user_version", "application_id"):
            digest.update(f"{pragma}={db.execute(f'PRAGMA {pragma}').fetchone()[0]};".encode())
        return digest.hexdigest()


def snapshot(database: Path, bundle: Path) -> dict:
    database = database.resolve()
    before = fingerprint(database)
    bundle.mkdir(parents=True, exist_ok=False)
    backup = bundle / "database.sqlite3"
    with closing(read_only(database)) as src, closing(sqlite3.connect(backup)) as dst:
        src.backup(dst)
    if fingerprint(backup) != before:
        raise ValueError("database changed during cold snapshot; writers must be stopped")
    metadata = dict(
        schema_version=1, database=str(database), sha256=sha(backup), fingerprint=before
    )
    temporary = bundle / "metadata.tmp"
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(bundle / "metadata.json")
    return metadata


def restore(bundle: Path) -> dict:
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("schema_version") != 1:
        raise ValueError("unknown database snapshot format")
    database = Path(metadata["database"])
    if not database.is_absolute():
        raise ValueError("database context is not absolute")
    backup = bundle / "database.sqlite3"
    if sha(backup) != metadata["sha256"] or fingerprint(backup) != metadata["fingerprint"]:
        raise ValueError("database snapshot verification failed")
    try:
        if fingerprint(database) == metadata["fingerprint"]:
            return dict(restored=False, fingerprint=metadata["fingerprint"])
    except (sqlite3.Error, OSError, ValueError):
        pass  # damaged/missing destination may still be recovered from verified backup
    temporary = database.with_name(database.name + ".restore-" + uuid4().hex)
    with backup.open("rb") as src, temporary.open("xb") as dst:
        shutil.copyfileobj(src, dst)
        dst.flush()
        os.fsync(dst.fileno())
    if sha(temporary) != metadata["sha256"]:
        raise ValueError("restore copy verification failed")
    failed = bundle / "failed-database"
    if failed.exists():
        failed = bundle / ("failed-database-" + uuid4().hex)
    failed.mkdir()
    # Preserve ALL failed-target state before replacing it. A stale WAL must
    # never be replayed onto the restored old schema. No app may be running.
    for suffix in ("", "-wal", "-shm", "-journal"):
        original = Path(str(database) + suffix)
        if original.exists():
            shutil.move(str(original), str(failed / ("database.sqlite3" + suffix)))
    os.replace(temporary, database)
    if fingerprint(database) != metadata["fingerprint"]:
        raise ValueError("restored schema/data verification failed")
    return dict(restored=True, fingerprint=metadata["fingerprint"], quarantine=str(failed))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "restore"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--install-dir", type=Path)
    args = parser.parse_args()
    if args.action == "restore":
        result = restore(args.bundle)
    else:
        if args.install_dir is None:
            parser.error("snapshot requires --install-dir")
        root = args.install_dir.resolve()
        os.chdir(root)
        sys.path[:0] = [str(root), str(root / "site-packages"), str(root / "backend")]
        # For new clients use the actual runtime Settings path. An immutable
        # old client inherits its launcher's env/.env: resolve using ITS config,
        # before updating files, never guessing a second default database.
        explicit = os.environ.get("VIRA_UPDATE_DATABASE_PATH")
        if explicit:
            database = Path(explicit)
        else:
            from app.config import load_settings

            database = Path(load_settings().sqlite_database_path)
        result = snapshot(database, args.bundle)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()

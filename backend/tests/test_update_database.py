"""Cold post-stop updater DB snapshots, not Alembic downgrade or raw live copies."""

from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "profile"))


def tool():
    spec = importlib.util.spec_from_file_location(
        "update_database", ROOT / "scripts/update_database.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('0005_pricing_settings'); CREATE TABLE ledger(id TEXT PRIMARY KEY,amount INTEGER NOT NULL); INSERT INTO ledger VALUES('one',1234567891234);"
        )


def test_restore_real_changed_schema_and_exact_values(tmp_path):
    t = tool()
    path = tmp_path / "داده با فاصله.sqlite3"
    sample(path)
    before = t.fingerprint(path)
    bundle = tmp_path / "attempt"
    t.snapshot(path, bundle)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE new_catalog(id TEXT PRIMARY KEY); UPDATE alembic_version SET version_num='0006_probe'; INSERT INTO ledger VALUES('uncommitted-user-operation',99);"
        )
    assert t.fingerprint(path) != before
    assert t.restore(bundle)["restored"] is True
    assert t.fingerprint(path) == before
    assert (bundle / "failed-database" / "database.sqlite3").is_file()
    with closing(sqlite3.connect(bundle / "failed-database" / "database.sqlite3")) as db, db:
        assert db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0] == 2


def test_unchanged_database_not_rewritten(tmp_path):
    t = tool()
    path = tmp_path / "db.sqlite3"
    sample(path)
    t.snapshot(path, tmp_path / "attempt")
    before = path.read_bytes()
    assert t.restore(tmp_path / "attempt")["restored"] is False
    assert path.read_bytes() == before


def test_wal_snapshot_and_restore(tmp_path):
    t = tool()
    path = tmp_path / "db.sqlite3"
    sample(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("INSERT INTO ledger VALUES('wal',321)")
        db.commit()
        t.snapshot(path, tmp_path / "attempt")
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DELETE FROM ledger WHERE id='wal'")
    t.restore(tmp_path / "attempt")
    with closing(sqlite3.connect(path)) as db, db:
        assert db.execute("SELECT amount FROM ledger WHERE id='wal'").fetchone()[0] == 321
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_corrupt_snapshot_does_not_touch_live_database(tmp_path):
    t = tool()
    path = tmp_path / "db.sqlite3"
    sample(path)
    t.snapshot(path, tmp_path / "attempt")
    original = path.read_bytes()
    (tmp_path / "attempt/database.sqlite3").write_bytes(b"bad")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        t.restore(tmp_path / "attempt")
    assert path.read_bytes() == original


def test_missing_database_not_created(tmp_path):
    t = tool()
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        t.snapshot(path, tmp_path / "attempt")
    assert not path.exists()


def test_snapshot_complete_current_schema_and_restart_reader(database, tmp_path):
    t = tool()
    path = database.settings.sqlite_database_path
    database.dispose()
    t.snapshot(path, tmp_path / "attempt")
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE candidate_probe(id TEXT PRIMARY KEY)")
    t.restore(tmp_path / "attempt")
    assert t.fingerprint(path) == t.fingerprint(tmp_path / "attempt/database.sqlite3")


async def test_update_lock_prevents_acknowledged_business_writes(client, database):
    lock = database.settings.data_dir / "updates/.update.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    assert not lock.exists()
    lock.write_text('{"pid":123,"attempt_id":"test"}')
    try:
        response = await client.post(
            "/api/v1/accounts",
            json={"code": "9900", "name": "must not exist", "account_type": "ASSET"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "update_in_progress"
        assert response.headers["retry-after"] == "3"
        assert (await client.get("/api/v1/health/ready")).status_code == 200
    finally:
        lock.unlink()
    assert (
        await client.post(
            "/api/v1/accounts",
            json={"code": "9900", "name": "can exist after commit", "account_type": "ASSET"},
        )
    ).status_code == 201


def test_recurring_jobs_wait_for_update_commit(database, monkeypatch):
    from app.services.scheduler import RecurringEntryService, SchedulerManager

    called = []
    monkeypatch.setattr(RecurringEntryService, "run_due_jobs", lambda self: called.append(1) or [])
    blocked = [True]
    scheduler = SchedulerManager(database.session_factory, write_gate=lambda: blocked[0])
    scheduler._tick()
    assert called == []
    blocked[0] = False
    scheduler._tick()
    assert called == [1]


def test_native_gate_imports_when_script_directory_is_not_repo_root(tmp_path):
    import os
    import subprocess
    import sys

    code = f"import runpy; ns=runpy.run_path({str(ROOT / 'scripts/update_native_smoke.py')!r},run_name='import_test'); assert callable(ns['fingerprint'])"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

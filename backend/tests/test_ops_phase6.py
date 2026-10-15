"""Phase 6 ops tests: safe migration lifecycle, System & Operations API,
health readiness with scheduler status."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


# ------------------------------------------------- migration lifecycle ---
def test_migration_lifecycle_bootstrap_backup_gate(tmp_path: Path) -> None:
    import migrate_vira

    db = tmp_path / "data" / "vira.sqlite3"
    report_path = tmp_path / "report.json"
    report = migrate_vira.run_migration(db, report_path)
    assert report["status"] == "migrated"
    assert report["post"]["alembic_revision"] == "0003_security"
    assert report["post"]["integrity_check"] == "ok"
    assert report["post"]["foreign_key_violations"] == 0
    # verified backup was taken before the schema change
    backup = Path(report["backup"])
    assert backup.exists()
    assert report_path.exists()
    # lock released
    assert not db.with_suffix(".sqlite3.migrate.lock").exists()


def test_migration_lock_blocks_second_process(tmp_path: Path) -> None:
    import migrate_vira

    db = tmp_path / "vira.sqlite3"
    migrate_vira._connect(db).close()
    lock = migrate_vira.acquire_lock(db)
    assert lock.exists()
    with pytest.raises(migrate_vira.MigrationError):
        migrate_vira.acquire_lock(db)
    lock.unlink()
    # stale lock (>1h) is reclaimed
    import os
    import time

    lock = migrate_vira.acquire_lock(db)
    old = time.time() - 4000
    os.utime(lock, (old, old))
    lock2 = migrate_vira.acquire_lock(db)
    assert lock2.exists()
    lock2.unlink()


def test_restore_bundle_roundtrip(tmp_path: Path) -> None:
    import migrate_vira

    db = tmp_path / "data" / "vira.sqlite3"
    report = migrate_vira.run_migration(db, None)
    restored = tmp_path / "restored.sqlite3"
    result = migrate_vira.restore_bundle(Path(report["backup"]).parent, restored)
    assert result["invariants"]["integrity_check"] == "ok"
    assert restored.exists()


# --------------------------------------------------- system API (sudo) ---
async def test_system_status_and_backup_flow(client, database, tmp_path) -> None:
    # sudo required for the whole area
    r = await client.get("/api/v1/system/status")
    assert r.status_code == 403
    sudo = await client.post("/api/v1/auth/sudo", json={"password": "test-password-1"})
    token = sudo.json()["sudo_token"]
    headers = {"X-Sudo-Token": token}
    r = await client.get("/api/v1/system/status", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["alembic_revision"] == "0003_security"
    assert body["version"]
    assert "scheduler" in body or "scheduler_enabled" in body
    # one-click encrypted backup
    r = await client.post("/api/v1/system/backup", headers=headers)
    assert r.status_code == 200, r.text
    bundle = r.json()
    assert bundle["encrypted"] is True
    assert Path(bundle["snapshot"]).exists()
    # path-traversal guarded download
    r = await client.get(
        "/api/v1/system/backup/download",
        params={"path": "/etc/passwd"},
        headers=headers,
    )
    assert r.status_code == 404
    r = await client.get(
        "/api/v1/system/backup/download",
        params={"path": bundle["dir"]},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.content[:16] == b"SQLite format 3\x00" or len(r.content) > 0
    # restore-verification drill
    r = await client.post(
        "/api/v1/system/backup/verify",
        params={"path": bundle["dir"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    verify = r.json()
    assert verify["ok"] is True
    assert verify["integrity_check"] == "ok"
    assert verify["debits_equal_credits"] is True
    # last_backup now populated
    r = await client.get("/api/v1/system/status", headers=headers)
    assert r.json()["last_backup"]["at"] is not None
    # security events recorded
    with database.session() as s:
        from sqlalchemy import select

        from app.models import SecurityAuditLog

        events = (
            s.execute(
                select(SecurityAuditLog).where(
                    SecurityAuditLog.event == "BACKUP_EXPORTED"
                )
            )
            .scalars()
            .all()
        )
    assert len(events) >= 2


async def test_check_updates_degrades_gracefully(client) -> None:
    sudo = await client.post("/api/v1/auth/sudo", json={"password": "test-password-1"})
    token = sudo.json()["sudo_token"]
    r = await client.get("/api/v1/system/check-updates", headers={"X-Sudo-Token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["current"]
    # offline/sandbox: checked=False with a reason; never a crash
    assert "update_available" in body
    if not body["checked"]:
        assert body["reason"]


async def test_health_ready_includes_scheduler(client) -> None:
    r = await client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ready", "degraded")
    assert body["scheduler"]["enabled"] is False or body["scheduler"]["running"] is True
    assert body["alembic_revision"] in ("0003_security", None)


def test_version_info_shape() -> None:
    from app.version import version_info

    info = version_info()
    assert {"version", "commit"} <= set(info)  # + built_at since v1.0.5
    assert info["version"]
    assert info["commit"]


def test_logging_rotation_install(tmp_path: Path) -> None:
    import logging

    from app.logging_setup import install_file_logging

    log_path = install_file_logging(tmp_path)
    assert log_path is not None and log_path.exists()
    logging.getLogger("vira-test").info("hello rotation")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "hello rotation" in log_path.read_text(encoding="utf-8")

"""Regressions for stuck 0-byte updates: real API/progress, safe staging, WAL backup."""

from __future__ import annotations

import asyncio
import io
import json
import sqlite3
import threading
import zipfile
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.services import update
from app.services.errors import DomainError
from app.services.update_engine import VerificationError, sha256_bytes


def delta_bytes(extra: dict[str, bytes] | None = None, **over: object) -> bytes:
    helper, content = b"MZ-fixture-helper", b"new code"
    members = {
        "vira-updater.exe": helper,
        "files/app/new.py": content,
        "version.json": b'{"version":"2.0.0"}',
        "install_manifest.json": b'{"files":[]}',
    }
    doc = {
        "base_version": "1.5.0", "target_version": "2.0.0",
        "operations": [{"op": "add", "path": "app/new.py", "sha256": sha256_bytes(content), "size": len(content)}],
        "hashes": {"vira-updater.exe": sha256_bytes(helper), "files/app/new.py": sha256_bytes(content)},
    } | over
    members["update.json"] = json.dumps(doc).encode()
    members.update(extra or {})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, value in members.items():
            # ZipInfo normalizes host separators on Windows. Preserve the raw
            # attack name so this fixture really tests backslash rejection there.
            info = zipfile.ZipInfo(name)
            info.filename = name
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, value)
    return out.getvalue()


def check_for(payload: bytes) -> update.UpdateCheckResult:
    return update.UpdateCheckResult(
        "1.5.0", "2.0.0", True, True,
        choice=update.PackageChoice("delta", [{"url": "https://github.com/x/y/d.zip", "size": len(payload),
            "sha256": sha256_bytes(payload), "from_version": "1.5.0"}], len(payload)),
    )


def stub_stream(monkeypatch, payload: bytes, *, status: int = 200, hook=None) -> None:
    class Stream:
        status_code = status

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            httpx.Response(status, request=httpx.Request("GET", "https://github.com/x/y/d.zip")).raise_for_status()

        def iter_bytes(self, n):
            yield payload[:10]
            if hook:
                hook()
            yield payload[10:]

    monkeypatch.setattr(httpx, "stream", lambda *args, **kw: Stream())


def test_verified_delta_is_extracted_before_staged(tmp_path, monkeypatch):
    manager = update.UpdateManager()
    payload = delta_bytes()
    observed = []
    stub_stream(monkeypatch, payload, hook=lambda: observed.append(manager.status()))
    status = manager.start_download(check_for(payload), Settings(data_dir=tmp_path))
    assert observed[0]["state"] == "downloading"
    assert observed[0]["downloaded_bytes"] == 10
    assert status["state"] == "staged" and status["verified"]
    stage = Path(status["staged_path"])
    assert (stage / "update.json").is_file()
    assert (stage / "vira-updater.exe").is_file()
    assert (stage / "files/app/new.py").read_bytes() == b"new code"
    assert "verified" in Path(status["log_path"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("extra,over", [
    ({"../../escape": b"bad"}, {}),
    ({"C:/escape": b"bad"}, {}),
    ({"files\\escape": b"bad"}, {}),
    ({"vira-updater.exe ": b"Windows alias"}, {}),
    ({"files/CON.txt": b"reserved device"}, {}),
    ({"VERSION.JSON": b"duplicate on Windows"}, {}),
    ({}, {"target_version": "9.9.9"}),
    ({}, {"hashes": {"vira-updater.exe": "ff" * 32}}),
    ({}, {"operations": [{"op": "delete", "path": "../data/vira.sqlite3"}]}),
])
def test_invalid_delta_cannot_be_applied(tmp_path, monkeypatch, extra, over):
    manager = update.UpdateManager()
    payload = delta_bytes(extra, **over)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(extra).issubset(archive.namelist())  # fixture must retain attack names
    stub_stream(monkeypatch, payload)
    with pytest.raises((VerificationError, ValueError)):
        manager.start_download(check_for(payload), Settings(data_dir=tmp_path))
    status = manager.status()
    assert status["state"] == "failed" and not status["verified"]
    assert status["staged_path"] == ""
    assert not list(tmp_path.rglob("new.py"))
    assert Path(status["log_path"]).is_file()


@pytest.mark.parametrize("failure", ["timeout", "network", "http404", "truncated", "bad_hash"])
def test_download_failure_is_visible_logged_and_retryable(tmp_path, monkeypatch, failure):
    payload = delta_bytes()
    check = check_for(payload)
    manager = update.UpdateManager()
    settings = Settings(data_dir=tmp_path)
    if failure in ("timeout", "network"):
        exc = httpx.ReadTimeout("timed out") if failure == "timeout" else httpx.ConnectError("offline")
        def broken(*args, **kw):
            raise exc
        monkeypatch.setattr(httpx, "stream", broken)
    else:
        stub_stream(monkeypatch, payload[:-10] if failure == "truncated" else payload,
                    status=404 if failure == "http404" else 200)
        if failure == "bad_hash":
            check.choice.packages[0]["sha256"] = "ff" * 32
    initial = manager.prepare_download(check, settings)
    assert initial["state"] == "downloading" and initial["log_path"]
    with pytest.raises(DomainError):
        manager.prepare_download(check, settings)
    manager.finish_download(check)  # no unhandled exception after HTTP response
    status = manager.status()
    assert status["state"] == "failed" and status["error_fa"]
    assert "بازگردانی" not in status["error_fa"]  # no fake rollback before any install
    assert "FAILED" in Path(status["log_path"]).read_text(encoding="utf-8")
    assert not list(tmp_path.rglob("*.part"))
    stub_stream(monkeypatch, payload)
    success = manager.start_download(check_for(payload), settings)
    assert success["state"] == "staged"
    assert success["log_path"] != status["log_path"]


def test_no_full_installer_or_chain_is_silently_downloaded(tmp_path):
    check = check_for(delta_bytes())
    for kind in ("full", "delta_chain"):
        check.choice.kind = kind
        with pytest.raises(DomainError):
            update.UpdateManager().prepare_download(check, Settings(data_dir=tmp_path))
    assert not list(tmp_path.iterdir())


async def test_api_returns_initial_state_and_allows_progress_polling(client, app, tmp_path, monkeypatch):
    payload = delta_bytes()
    check = check_for(payload)
    manager = update.UpdateManager()
    monkeypatch.setattr(update, "manager", manager)
    monkeypatch.setattr(update, "check_for_update", lambda *a: check)
    app.state.settings = Settings(data_dir=tmp_path, sqlite_database_path=app.state.settings.sqlite_database_path,
                                  session_secret=app.state.settings.session_secret)
    entered, release = threading.Event(), threading.Event()
    def pause():
        entered.set()
        assert release.wait(5)
    stub_stream(monkeypatch, payload, hook=pause)
    sudo = await client.post("/api/v1/auth/sudo", json={"password": "test-password-1"})
    headers = {"X-Sudo-Token": sudo.json()["sudo_token"]}
    request = asyncio.create_task(client.post("/api/v1/system/update/download", headers=headers))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        progress = await client.get("/api/v1/system/update/status", headers=headers)
        assert progress.json()["downloaded_bytes"] == 10
        assert progress.json()["state"] == "downloading"
    finally:
        release.set()
    response = await request
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "downloading"  # response not blocked on completing download
    final = await client.get("/api/v1/system/update/status", headers=headers)
    assert final.json()["state"] == "staged"


def test_pre_update_backup_includes_wal_commits(tmp_path, monkeypatch):
    manager = update.UpdateManager()
    payload = delta_bytes()
    stub_stream(monkeypatch, payload)
    db = tmp_path / "live.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE alembic_version(version_num TEXT)")
    connection.execute("INSERT INTO alembic_version VALUES ('0004_operations')")
    connection.execute("CREATE TABLE sentinel(value TEXT)")
    connection.execute("INSERT INTO sentinel VALUES ('committed-in-wal')")
    connection.commit()
    settings = Settings(data_dir=tmp_path, sqlite_database_path=db)
    manager.start_download(check_for(payload), settings)
    monkeypatch.setattr(update, "manager", manager)
    monkeypatch.setattr(update, "launch_updater", lambda *args: manager.status())
    try:
        result = update.apply_update(settings)
        with sqlite3.connect(result["pre_update_backup"]) as backup:
            assert backup.execute("SELECT value FROM sentinel").fetchone()[0] == "committed-in-wal"
    finally:
        connection.close()


def test_backup_failure_prevents_helper_launch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    manager = update.UpdateManager()
    payload = delta_bytes()
    stub_stream(monkeypatch, payload)
    db = tmp_path / "live.sqlite3"
    db.touch()
    settings = Settings(data_dir=tmp_path, sqlite_database_path=db)
    manager.start_download(check_for(payload), settings)
    monkeypatch.setattr(update, "manager", manager)
    monkeypatch.setattr("app.services.backup.create_backup", lambda *args: SimpleNamespace(ok=False))
    def must_not_launch(*args):
        pytest.fail("helper launched without a verified backup")
    monkeypatch.setattr(update, "launch_updater", must_not_launch)
    with pytest.raises(DomainError, match="پشتیبان"):
        update.apply_update(settings)
    assert manager.status()["state"] == "failed"


async def test_download_requires_sudo_before_reserving_a_job(client, monkeypatch):
    manager = update.UpdateManager()
    monkeypatch.setattr(update, "manager", manager)
    response = await client.post("/api/v1/system/update/download")
    assert response.status_code == 403
    assert manager.status()["state"] == "idle"


def test_release_generator_output_can_be_staged(tmp_path):
    """Exercise the real ZIP producer, including bsdiff members, not only fixtures."""
    import subprocess
    import sys

    from app.services.update_engine import build_manifest, manifest_to_json
    from app.services.update_staging import extract_delta

    base, target = tmp_path / "base", tmp_path / "target"
    for root, version, content in ((base, "1.5.0", b"old" * 100), (target, "2.0.0", b"new" * 100)):
        (root / "app").mkdir(parents=True)
        (root / "app" / "module.py").write_bytes(content)
        (root / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        (root / "vira-updater.exe").write_bytes(b"MZ-fixture-helper")
    manifest = base / "install_manifest.json"
    manifest.write_text(json.dumps(manifest_to_json(build_manifest(base))), encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "scripts" / "gen_delta.py"
    subprocess.run([
        sys.executable, str(script), "--base-manifest", str(manifest), "--base-dir", str(base),
        "--target-dir", str(target), "--base-version", "1.5.0", "--target-version", "2.0.0",
        "--out", str(tmp_path), "--patch-threshold", "100",
    ], check=True, capture_output=True)
    stage = tmp_path / "payload"
    extract_delta(tmp_path / "VIRA-v2.0.0-delta-from-v1.5.0.zip", stage, "1.5.0", "2.0.0")
    doc = json.loads((stage / "update.json").read_text(encoding="utf-8"))
    assert any(op["op"] == "patch" for op in doc["operations"])
    assert (stage / "vira-updater.exe").read_bytes() == b"MZ-fixture-helper"
    assert (stage / "version.json").is_file()

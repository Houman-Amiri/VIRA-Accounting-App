"""Private restart/write quarantine controls; synthetic state, no native execution."""

from __future__ import annotations

import json

import httpx
import pytest

from app import desktop_entry as entry
from app.config import Settings
from app.main import create_app
from app.private_pdf_bootstrap import _no_links


def setup(tmp_path, monkeypatch):
    root = tmp_path / "installed payload"
    state = tmp_path / "profile/VIRA/private-native-installed/state"
    state.mkdir(parents=True)
    (state / "private-desktop-state.json").write_text(
        json.dumps(dict(schema=1, role="PRIVATE_SOURCE_DESKTOP_STATE", payload_root=str(root)))
    )
    lock = state / "data/updates/.update.lock"
    lock.parent.mkdir(parents=True)
    token = "a" * 64
    lock.write_bytes(token.encode())
    native = state.parent / ".native-update.lock"
    native.write_text(json.dumps(dict(pid=123, token=token)))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "profile"))
    monkeypatch.setenv("VIRA_PRIVATE_UPDATE_TOKEN", token)
    return root, state, lock, native


@pytest.mark.parametrize(
    "fault",
    [
        "legacy",
        "missing-token",
        "wrong-token",
        "wrong-lock",
        "missing-native",
        "wrong-owner",
        "bad-pid",
        "foreign-state",
        "link",
    ],
)
def test_no_generic_startup_bypass_during_private_update(tmp_path, monkeypatch, fault):
    root, state, lock, native = setup(tmp_path, monkeypatch)
    if fault == "missing-token":
        monkeypatch.delenv("VIRA_PRIVATE_UPDATE_TOKEN")
    if fault == "wrong-token":
        monkeypatch.setenv("VIRA_PRIVATE_UPDATE_TOKEN", "b" * 64)
    if fault == "wrong-lock":
        lock.write_bytes(b"foreign token")
    if fault == "missing-native":
        native.unlink()
    if fault == "wrong-owner":
        native.write_text(json.dumps(dict(pid=123, token="c" * 64)))
    if fault == "bad-pid":
        native.write_text(json.dumps(dict(pid=True, token="a" * 64)))
    if fault == "foreign-state":
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "other-profile"))
    if fault == "link":
        saved = native.with_suffix(".saved")
        native.rename(saved)
        native.symlink_to(saved)
    before = lock.read_bytes()
    with (
        pytest.raises(ValueError),
        entry.state_guard(root, state, _no_links, installed_restart=fault != "legacy"),
    ):
        pytest.fail("Unowned restart must not enter application body")
    assert lock.read_bytes() == before
    assert not (state / ".desktop.lock").exists()


async def test_controller_child_can_become_ready_without_acknowledging_user_writes(
    tmp_path, monkeypatch
):
    root, state, lock, native = setup(tmp_path, monkeypatch)
    settings = Settings(
        _env_file=None,
        data_dir=state / "data",
        sqlite_database_path=state / "data/data/vira.sqlite3",
        scheduler_enabled=False,
        session_secret="synthetic-secret-long-enough-not-a-real-credential",
    )
    with entry.state_guard(root, state, _no_links, installed_restart=True):
        app = create_app(settings)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/api/v1/health/live")).status_code == 200
                # Same production ASGI middleware that protects all business,
                # auth, ingestion and privileged mutation routes, BEFORE handlers.
                for path in ("/api/v1/accounts", "/api/v1/auth/login", "/api/v1/auth/sudo"):
                    response = await client.post(path, json={})
                    assert response.status_code == 503
                    assert response.json()["code"] == "update_in_progress"
                    assert response.headers["retry-after"] == "3"
                assert lock.read_bytes() == b"a" * 64 and native.is_file()
                lock.unlink()  # Simulated controller durable-terminal boundary only.
                assert (
                    await client.post("/api/v1/accounts", json={})
                ).status_code == 403  # Existing CSRF gate, no bypass.
        finally:
            app.state.database.dispose()
    assert not (state / ".desktop.lock").exists()
    assert native.exists()  # The entry never removes the controller's ownership lock.

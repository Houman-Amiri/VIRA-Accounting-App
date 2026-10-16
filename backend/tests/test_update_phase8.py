"""Phase 8: authenticated discovery, pinned consent and durable truthful outcome."""

from __future__ import annotations

import json

import pytest

from app.services import update
from tests.test_update_download_flow import check_for, delta_bytes


async def test_discovery_and_progress_need_login_but_not_sudo(client, anon_client, monkeypatch):
    monkeypatch.setattr(update, "manager", update.UpdateManager())
    monkeypatch.setattr(update, "check_for_update", lambda *args: check_for(delta_bytes()))
    assert (await client.get("/api/v1/system/check-updates")).status_code == 200
    assert (await client.get("/api/v1/system/update/status")).status_code == 200
    # Financial backup/status did NOT lose their step-up guard.
    assert (await client.get("/api/v1/system/status")).status_code == 403
    assert (await client.post("/api/v1/system/backup")).status_code == 403
    client.cookies.clear()
    assert (await anon_client.get("/api/v1/system/check-updates")).status_code == 401
    assert (await anon_client.get("/api/v1/system/update/status")).status_code == 401


@pytest.mark.parametrize("change", ["version", "sha256", "full"])
async def test_changed_package_cannot_be_downloaded_under_old_consent(
    client, database, monkeypatch, change
):
    payload = delta_bytes()
    check = check_for(payload)
    manager = update.UpdateManager()
    monkeypatch.setattr(update, "manager", manager)
    monkeypatch.setattr(update, "check_for_update", lambda *args: check)
    if change == "version":
        check.latest = "2.0.1"
    elif change == "sha256":
        check.choice.packages[0]["sha256"] = "ff" * 32
    else:
        check.choice.kind = "full"
    sudo = (await client.post("/api/v1/auth/sudo", json={"password": "test-password-1"})).json()
    from app.services.update_engine import sha256_bytes

    response = await client.post(
        "/api/v1/system/update/download",
        headers={"X-Sudo-Token": sudo["sudo_token"]},
        json={"expected_version": "2.0.0", "expected_sha256": sha256_bytes(payload)},
    )
    assert response.status_code == 400, response.text
    assert manager.status()["state"] == "idle"
    assert not list(database.settings.data_dir.glob("updates/*/package.zip*"))


def test_helper_outcome_survives_backend_restart_without_finishing_another_job(
    tmp_path, monkeypatch
):
    from app.config import Settings

    path = tmp_path / "updates/last-result.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            dict(
                state="rolled_back",
                target_version="2.0.0",
                log_path="attempt-1",
                error_fa="تأیید بازگردانی",
            )
        )
    )
    manager = update.UpdateManager()
    monkeypatch.setattr(update, "manager", manager)
    result = update.read_update_status(Settings(data_dir=tmp_path))
    assert result["state"] == "rolled_back" and result["error_fa"] == "تأیید بازگردانی"
    manager._job.state = "applying"
    manager._job.log_path = "attempt-2"
    assert update.read_update_status(Settings(data_dir=tmp_path))["state"] == "applying"
    manager._job.log_path = "attempt-1"
    assert update.read_update_status(Settings(data_dir=tmp_path))["state"] == "rolled_back"
    path.write_text("{corrupt")
    assert update.read_update_status(Settings(data_dir=tmp_path))["state"] == "applying"


def test_no_direct_delta_requires_manual_action_never_auto_full(tmp_path, monkeypatch):
    from app.config import Settings
    from tests.test_update_service import _latest_bytes, _Resp

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _Resp(200, _latest_bytes()))
    result = update.check_for_update(
        "1.0.0", Settings(data_dir=tmp_path, app_update_url="https://example.test/latest.json")
    )
    assert result.manual_required
    assert "متوقف" in result.reason_fa
    with pytest.raises(Exception, match="متوقف"):
        update.UpdateManager().prepare_download(result, Settings(data_dir=tmp_path))
    assert not (tmp_path / "updates").exists()

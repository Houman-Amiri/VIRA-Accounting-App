"""Synthetic entry contracts + Linux TCP lifecycle, NOT Windows/native proof."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import httpx
import pytest

from app import desktop_entry as entry
from app.private_pdf_bootstrap import _no_links

ROOT = Path(__file__).resolve().parents[2]


def options(state):
    return {
        "role": "PRIVATE_SOURCE_DESKTOP_REQUEST",
        "manifest_sha256": "a" * 64,
        "inventory_sha256": "b" * 64,
        "source_audit_sha256": "c" * 64,
        "state_root": str(state),
        "launch_id": "d" * 32,
        "port": 0,
        "no_browser": True,
    }


def test_request_explicit_private_disjoint_profile(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(profile))
    file = tmp_path / "request.json"
    value = options(profile / "private")
    entry.write(file, value)
    assert entry.request(tmp_path / "payload", file) == value
    for key, bad in [
        ("port", True),
        ("port", -1),
        ("no_browser", "true"),
        ("launch_id", "../bad"),
        ("source_audit_sha256", None),
        ("state_root", str(profile)),
        ("role", "ordinary"),
    ]:
        changed = dict(value)
        changed[key] = bad
        entry.write(file, changed)
        with pytest.raises((ValueError, TypeError)):
            entry.request(tmp_path / "payload", file)
    file.write_bytes(b'{"role":1,"role":2}')
    with pytest.raises(ValueError, match="Duplicate"):
        entry.request(tmp_path / "payload", file)


def test_guard_preserves_owned_state_and_blocks_duplicates_updates(tmp_path):
    root = tmp_path / "payload"
    state = tmp_path / "state"
    with entry.state_guard(root, state, _no_links):
        with pytest.raises(FileExistsError), entry.state_guard(root, state, _no_links):
            pass
        assert (state / ".desktop.lock").exists()
    assert not (state / ".desktop.lock").exists()
    lock = state / "data/updates/.update.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"updating")
    with pytest.raises(ValueError, match="Update"), entry.state_guard(root, state, _no_links):
        pass
    assert lock.read_bytes() == b"updating" and not (state / ".desktop.lock").exists()
    marker = state / "private-desktop-state.json"
    marker.write_bytes(b"{}")
    with (
        pytest.raises(ValueError, match="Existing state"),
        entry.state_guard(root, state, _no_links),
    ):
        pass


def test_guard_rejects_descendant_symlink_before_writes(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    # Windows CI is not assumed to have symlink privileges. Mock a reparse point
    # instead there; real Unicode/NTFS/process checks are in the native workflow.
    child = state / "data"
    child.mkdir()

    def check(path):
        _no_links(path)
        if path == child:
            raise ValueError("Simulated reparse point")

    with (
        pytest.raises(ValueError, match="reparse"),
        entry.state_guard(tmp_path / "payload", state, check),
    ):
        pass
    assert not (state / "private-desktop-state.json").exists()


def test_real_cmd_default_body_unchanged_and_private_branch_before_cd():
    cmd = (ROOT / "scripts/start_vira.cmd").read_text()
    assert cmd.index("goto :private_source_candidate") < cmd.index('cd /d "%~dp0"')
    branch = cmd.split("\n:private_source_candidate\n", 1)[-1]
    assert branch.index("DisableDelayedExpansion") < branch.index("%~dp0")
    assert "-I -S -B -X utf8" in branch and "app\\desktop_entry.py" in branch
    assert "GITHUB_ACTIONS" in branch
    assert "pdf_private_http_probe" not in (ROOT / "backend/app/desktop_entry.py").read_text()


def test_credential_failure_precedes_any_database_or_secret_write(tmp_path, monkeypatch):
    monkeypatch.delenv("VIRA_ADMIN_PASSWORD", raising=False)
    state = tmp_path / "private"
    state.mkdir()
    with pytest.raises(ValueError, match="credential"):
        entry.serve(ROOT, state, tmp_path, options(state))
    assert list(state.iterdir()) == []


def test_linux_actual_migration_seed_tcp_ready_stop_restart(tmp_path, monkeypatch):
    # Only native inspection is substituted; no Windows/source/ACP claim here.
    monkeypatch.setattr(entry, "native_state", lambda *_: {"synthetic_not_native": True})
    monkeypatch.setenv("VIRA_ADMIN_PASSWORD", "synthetic-test-owner-password-more-than-32")
    monkeypatch.setenv("FONTCONFIG_FILE", "synthetic-unused")
    state = tmp_path / "private"
    state.mkdir()
    original_sys_path = entry.sys.path[:]
    client_errors = []
    ready = []

    def client(launch):
        try:
            end = time.monotonic() + 35
            while not (launch / "ready.json").exists():
                if time.monotonic() > end:
                    raise RuntimeError("Linux readiness timed out")
                time.sleep(0.03)
            r = entry.read(launch / "ready.json")
            ready.append(r)
            with httpx.Client(base_url=r["url"], trust_env=False) as http:
                response = http.post(
                    "/api/v1/auth/login",
                    json={
                        "username": "owner",
                        "password": "synthetic-test-owner-password-more-than-32",
                    },
                )
                assert response.status_code == 200
                assert http.get("/api/v1/health/ready").json()["status"] == "ready"
            entry.write(launch / "stop.json", {"pid": entry.os.getpid(), "launch_id": "d" * 32})
        except BaseException as exc:
            client_errors.append(exc)

    try:
        results = []
        secret = None
        for i in range(2):
            launch = state / f"launch-{i}"
            launch.mkdir()
            worker = threading.Thread(target=client, args=(launch,), daemon=True)
            worker.start()
            results.append(entry.serve(ROOT, state, launch, options(state)))
            worker.join(timeout=5)
            assert not worker.is_alive() and not client_errors
            current = hashlib.sha256((state / "session.secret").read_bytes()).hexdigest()
            if secret is not None:
                assert current == secret
            secret = current
        assert [r["first_run"] for r in ready] == [True, False]
        assert [r["seed"]["users_created"] for r in results] == [1, 0]
        assert all(r["graceful_shutdown"] for r in results)
        assert results[0]["database"] == results[1]["database"]
    finally:
        entry.sys.path[:] = original_sys_path


def test_environment_restores_absent_and_existing(monkeypatch):
    monkeypatch.setenv("VIRA_ENTRY_TEST", "old")
    monkeypatch.delenv("VIRA_ENTRY_ABSENT", raising=False)
    with (
        pytest.raises(RuntimeError),
        entry.environment({"VIRA_ENTRY_TEST": "new", "VIRA_ENTRY_ABSENT": "new"}),
    ):
        raise RuntimeError("test")
    assert entry.os.environ["VIRA_ENTRY_TEST"] == "old"
    assert "VIRA_ENTRY_ABSENT" not in entry.os.environ


@pytest.mark.parametrize("message, code", [
    ("Audited desktop native module absent", "NATIVE_MODULE_ABSENT"),
    ("Foreign desktop native module", "FOREIGN_NATIVE_MODULE"),
    ("Desktop source function mismatch", "NATIVE_SOURCE_FUNCTION"),
    ("Desktop startup/monitor failed", "DESKTOP_MONITOR"),
    ("Unrecognized error with SECRET synthetic password", "RuntimeError"),
])
def test_bounded_startup_diagnostics_distinguish_known_failures_without_secrets(message, code):
    assert entry.failure_kind(RuntimeError(message)) == code

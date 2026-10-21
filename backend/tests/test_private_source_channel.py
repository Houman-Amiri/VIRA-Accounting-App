"""Synthetic channel/HTTP boundaries; no real interpreter/DLL/helper execution."""

from __future__ import annotations

import hashlib
import json
import zipfile
from contextlib import nullcontext
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.services import private_source_channel as channel
from app.services import update
from app.services.errors import DomainError
from app.services.update_engine import build_manifest, manifest_to_json, plan_delta
from app.services.update_staging import extract_delta


def raw(value):
    return json.dumps(value, indent=2).encode()


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "VIRA installed opaque"
    home = tmp_path / "profile" / "VIRA/private-native-installed"
    state = home / "state"
    state.mkdir(parents=True)
    root.mkdir()
    files = {
        "version.json": raw(dict(version="99.30.0", spa_build="old")),
        "vira-updater.exe": b"OPAQUE OLD HELPER NEVER EXECUTED",
        "native/pdf/runtime-inventory.json": raw({"synthetic": True}),
        "native/pdf/source-audit.json": raw({"synthetic_audit": True}),
        "native/pdf/bin/synthetic.dll": b"OPAQUE NOT A DLL",
    }
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    base = build_manifest(root)
    (root / "install_manifest.json").write_bytes(raw(manifest_to_json(base)))

    def sha(data):
        return hashlib.sha256(data).hexdigest()

    common = dict(
        schema=1,
        role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
        port=8787,
        no_browser=True,
        inventory_sha256=sha(files["native/pdf/runtime-inventory.json"]),
        source_audit_sha256=sha(files["native/pdf/source-audit.json"]),
    )
    old = dict(common, manifest_sha256=channel.sha(root / "install_manifest.json"))
    (home / "anchor.json").write_bytes(raw(old))
    (state / "private-desktop-state.json").write_bytes(
        raw(dict(schema=1, role="PRIVATE_SOURCE_DESKTOP_STATE", payload_root=str(root)))
    )
    settings = Settings(
        _env_file=None,
        data_dir=state / "data",
        sqlite_database_path=state / "data/data/vira.sqlite3",
    )
    monkeypatch.setenv("LOCALAPPDATA", str(home.parents[1]))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("VIRA_PRIVATE_INSTALLED_SOURCE", "1")
    monkeypatch.setattr(update, "install_root", lambda _: root)
    targetdir = tmp_path / "target"
    targetfiles = dict(files)
    targetfiles["version.json"] = raw(dict(version="99.30.1", spa_build="new"))
    targetfiles["vira-updater.exe"] = b"OPAQUE DOWNLOADED HELPER MUST NOT BE SELECTED"
    targetfiles["native/pdf/bin/synthetic.dll"] = b"OPAQUE CHANGED NATIVE-DIRECTORY BYTES"
    for name, data in targetfiles.items():
        p = targetdir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    target = build_manifest(targetdir)
    targetraw = raw(manifest_to_json(target))
    targetpin = dict(common, manifest_sha256=sha(targetraw))
    plan, members = plan_delta("99.30.0", "99.30.1", base, target, patch_threshold=1 << 20)
    contents = {
        "version.json": targetfiles["version.json"],
        "install_manifest.json": targetraw,
        "vira-updater.exe": targetfiles["vira-updater.exe"],
        "private-source-anchor.json": raw(targetpin),
    }
    for member, (_, name) in members.items():
        contents[member] = targetfiles[name]
    doc = plan.to_json()
    doc["hashes"] = {
        name: sha(data)
        for name, data in contents.items()
        if name not in {"version.json", "install_manifest.json"}
    }
    contents["update.json"] = raw(doc)
    archive = tmp_path / "package.zip"
    with zipfile.ZipFile(archive, "w") as packet:
        for name, data in contents.items():
            packet.writestr(name, data)
    return root, home, settings, archive, old


def test_private_stream_download_uses_existing_verifier_and_old_installed_helper(tmp_path, monkeypatch):
    root, home, settings, archive, old = fixture(tmp_path, monkeypatch)
    context = channel.scope(settings, root)
    assert context is not None and context.pin == old
    payload = archive.read_bytes()
    response = httpx.Response(
        200, content=payload, request=httpx.Request("GET", "https://example.test/delta.zip")
    )
    monkeypatch.setattr(httpx, "stream", lambda *a, **kw: nullcontext(response))
    check = update.UpdateCheckResult(
        current="99.30.0",
        latest="99.30.1",
        update_available=True,
        checked=True,
        choice=update.PackageChoice(
            kind="delta",
            packages=[
                dict(
                    from_version="99.30.0",
                    to_version="99.30.1",
                    url="https://example.test/delta.zip",
                    sha256=hashlib.sha256(payload).hexdigest(),
                    size=len(payload),
                )
            ],
            total_bytes=len(payload),
        ),
    )
    manager = update.UpdateManager()
    status = manager.start_download(check, settings)
    assert status["state"] == "staged" and status["verified"]
    stage = Path(status["staged_path"])
    assert stage.is_relative_to(home / "state/data/updates")
    argv, log = update._updater_command(settings, str(stage))
    assert argv[0] == str(root / "vira-updater.exe")
    assert argv[0] != str(stage / "vira-updater.exe")
    transaction = channel.read(Path(argv[argv.index("-PrivateSourceTransaction") + 1]))
    assert transaction["archive_sha256"] == hashlib.sha256(payload).hexdigest()
    assert not Path(transaction["attempt"]).is_relative_to(home)
    assert log == stage / "update.log"
    assert (root / "native/pdf/bin/synthetic.dll").read_bytes() == b"OPAQUE NOT A DLL"
    # Applying may only launch AFTER the API's existing backup/permission flow.
    assert manager.status()["state"] == "staged"


@pytest.mark.parametrize(
    "mutation", ["marker", "no-ci", "data", "database", "state-owner", "manifest", "pin-symlink"]
)
def test_env_marker_alone_cannot_select_private_source_channel(tmp_path, monkeypatch, mutation):
    root, home, settings, _, _ = fixture(tmp_path, monkeypatch)
    if mutation == "marker":
        monkeypatch.delenv("VIRA_PRIVATE_INSTALLED_SOURCE")
        assert channel.scope(settings, root) is None
        return
    if mutation == "no-ci":
        monkeypatch.setenv("GITHUB_ACTIONS", "false")
    if mutation == "data":
        settings.data_dir = tmp_path / "foreign-data"
    if mutation == "database":
        settings.sqlite_database_path = tmp_path / "foreign.sqlite3"
    if mutation == "state-owner":
        (home / "state/private-desktop-state.json").write_bytes(raw({"payload_root": "other"}))
    if mutation == "manifest":
        (root / "install_manifest.json").write_bytes(b"{}")
    if mutation == "pin-symlink":
        target = tmp_path / "moved-pin.json"
        (home / "anchor.json").rename(target)
        (home / "anchor.json").symlink_to(target)
    with pytest.raises(DomainError):
        channel.scope(settings, root)


@pytest.mark.parametrize(
    "mutation", ["public", "pin-hash", "manifest", "port", "unknown-role", "duplicate-anchor"]
)
def test_private_archive_binding_rejected_before_extraction(tmp_path, monkeypatch, mutation):
    _, _, _, archive, old = fixture(tmp_path, monkeypatch)
    with zipfile.ZipFile(archive) as packet:
        contents = {name: packet.read(name) for name in packet.namelist()}
    if mutation == "pin-hash":
        doc = json.loads(contents["update.json"])
        doc["hashes"]["private-source-anchor.json"] = "0" * 64
        contents["update.json"] = raw(doc)
    elif mutation == "manifest":
        contents["install_manifest.json"] += b" "
    elif mutation in {"port", "unknown-role", "duplicate-anchor"}:
        pin = json.loads(contents["private-source-anchor.json"])
        if mutation == "port":
            pin["port"] = 9999
        if mutation == "unknown-role":
            pin["role"] = "PUBLIC"
        contents["private-source-anchor.json"] = (
            raw(pin) if mutation != "duplicate-anchor" else b'{"role":"a","role":"b"}'
        )
        doc = json.loads(contents["update.json"])
        doc["hashes"]["private-source-anchor.json"] = hashlib.sha256(
            contents["private-source-anchor.json"]
        ).hexdigest()
        contents["update.json"] = raw(doc)
    with zipfile.ZipFile(archive, "w") as packet:
        for name, data in contents.items():
            packet.writestr(name, data)
    destination = tmp_path / "extraction"
    with pytest.raises(ValueError):
        extract_delta(
            archive,
            destination,
            "99.30.0",
            "99.30.1",
            private_pin=None if mutation == "public" else old,
        )
    assert not destination.exists()


def test_private_polling_survives_restart_and_ignores_previous_result(tmp_path, monkeypatch):
    root, home, settings, _, _ = fixture(tmp_path, monkeypatch)
    updates = home / "state/data/updates"
    updates.mkdir(parents=True)
    monkeypatch.setattr(update, "manager", update.UpdateManager())
    (home / ".native-channel.lock").write_bytes(raw(dict(pid=42, attempt_id="current")))
    previous = dict(state="committed", helper_pid=41, attempt_id="previous", verified=True)
    (updates / "last-result.json").write_bytes(raw(previous))
    status = update.read_update_status(settings)
    assert status["state"] == "applying" and not status["verified"]
    current = dict(
        state="rolled_back",
        helper_pid=42,
        attempt_id="current",
        verified=False,
        machine_state="rolled_back",
    )
    (updates / "last-result.json").write_bytes(raw(current))
    assert update.read_update_status(settings)["state"] == "rolled_back"


def test_changed_verified_archive_blocks_helper_selection(tmp_path, monkeypatch):
    root, _, settings, archive, old = fixture(tmp_path, monkeypatch)
    stage = settings.data_dir / "updates/99.30.1/attempt/payload"
    stage.parent.mkdir(parents=True)
    extract_delta(archive, stage, "99.30.0", "99.30.1", private_pin=old)
    (stage.parent / "package.zip").write_bytes(archive.read_bytes())
    channel.write_new(
        stage.parent / "source-download-receipt.json",
        dict(archive_sha256="0" * 64, base_version="99.30.0", target_version="99.30.1"),
    )
    with pytest.raises(DomainError):
        update._updater_command(settings, str(stage))


@pytest.mark.parametrize(
    "mutation",
    ["archive", "staged-manifest", "staged-pin", "helper", "base-version", "target-version"],
)
def test_apply_rechecks_download_and_installed_helper(tmp_path, monkeypatch, mutation):
    root, _, settings, archive, old = fixture(tmp_path, monkeypatch)
    stage = settings.data_dir / "updates/99.30.1/attempt/payload"
    stage.parent.mkdir(parents=True)
    extract_delta(archive, stage, "99.30.0", "99.30.1", private_pin=old)
    package = stage.parent / "package.zip"
    package.write_bytes(archive.read_bytes())
    channel.write_new(
        stage.parent / "source-download-receipt.json",
        dict(archive_sha256=channel.sha(package), base_version="99.30.0", target_version="99.30.1"),
    )
    victim = {
        "archive": package,
        "staged-manifest": stage / "install_manifest.json",
        "staged-pin": stage / "private-source-anchor.json",
        "helper": root / "vira-updater.exe",
        "base-version": root / "version.json",
        "target-version": stage / "version.json",
    }[mutation]
    victim.write_bytes(b"{}")
    with pytest.raises(DomainError):
        update._updater_command(settings, str(stage))
    assert not list(stage.parent.glob("private-transaction-*.json"))


def test_cli_manifest_bytes_match_private_delta_on_every_platform(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    root, _, _, _, old = fixture(tmp_path, monkeypatch)
    target = tmp_path / "target"
    unicode_file = target / "app/نام فارسی.py"
    unicode_file.parent.mkdir()
    unicode_file.write_bytes(b"# synthetic unchanged-source transport test")
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo / "scripts/build_manifest.py"), str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    manifest = (target / "install_manifest.json").read_bytes()
    assert b"\r\n" not in manifest and "نام فارسی".encode() in manifest
    targetpin = dict(old, manifest_sha256=hashlib.sha256(manifest).hexdigest())
    pin = tmp_path / "target-anchor.json"
    pin.write_bytes(raw(targetpin))
    args = [
        sys.executable,
        str(repo / "scripts/gen_delta.py"),
        "--base-manifest",
        str(root / "install_manifest.json"),
        "--base-dir",
        str(root),
        "--target-dir",
        str(target),
        "--base-version",
        "99.30.0",
        "--target-version",
        "99.30.1",
        "--out",
        str(tmp_path / "out"),
        "--private-source-anchor",
        str(pin),
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    package = next((tmp_path / "out").glob("*.zip"))
    with zipfile.ZipFile(package) as packet:
        assert packet.read("install_manifest.json") == manifest
        assert "files/native/pdf/runtime-inventory.json" not in packet.namelist()
        assert "files/native/pdf/source-audit.json" not in packet.namelist()
    extract_delta(package, tmp_path / "valid-stage", "99.30.0", "99.30.1", private_pin=old)
    # A native digest mismatch cannot produce an acceptable target package.
    pin.write_bytes(raw(dict(targetpin, inventory_sha256="0" * 64)))
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0
    result = subprocess.run(
        args, capture_output=True, text=True, env=dict(os.environ, GITHUB_ACTIONS="false")
    )
    assert result.returncode != 0 and "CI only" in result.stderr

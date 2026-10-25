"""External client protocol tests only; opaque fixtures are NEVER executable/native proof."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import sqlite3
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client_module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return runpy.run_path(str(ROOT / "scripts/phase3_native_transaction.py"))


def test_signed_loopback_feed_binds_exact_delta_bytes_and_never_serves_setup(
    tmp_path, client_module
):
    from cryptography.hazmat.primitives import serialization

    p = tmp_path / "opaque-delta.zip"
    p.write_bytes(b"OPAQUE protocol fixture NOT A NATIVE PACKAGE")
    with client_module["Feed"](tmp_path) as feed:
        package = feed.publish(p, "99.30.0", "99.30.1")
        with httpx.Client(trust_env=False) as h:
            raw = h.get(feed.url + "/latest.json").content
            sig = h.get(feed.url + "/latest.json.sig").content
            serialization.load_pem_public_key(feed.public.encode()).verify(sig, raw)
            assert h.get(package["url"]).content == p.read_bytes()
            assert json.loads(raw)["deltas"] == [package]
            assert package["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
            assert "/FORBIDDEN-FULL-SETUP.exe" not in feed.requests
            assert h.get(feed.url + "/FORBIDDEN-FULL-SETUP.exe").status_code == 500


def test_external_fingerprint_matches_cold_snapshot_identity_without_writing(
    tmp_path, client_module
):
    path = tmp_path / "synthetic.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('synthetic'); CREATE TABLE amounts(id TEXT, scaled INTEGER); INSERT INTO amounts VALUES('same-id',12345678901000);"
        )
    before = path.read_bytes()
    expected = runpy.run_path(str(ROOT / "scripts/update_database.py"))["fingerprint"](path)
    assert client_module["fingerprint"](path) == expected
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        db.execute("UPDATE amounts SET scaled=scaled+1")
    assert client_module["fingerprint"](path) != expected


def test_non_windows_native_client_rejects_before_cleanup_or_filesystem_changes(
    tmp_path, client_module, monkeypatch
):
    # No flag alone or fabricated folder may run native acceptance on this host.
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    before = list(tmp_path.rglob("*"))
    with pytest.raises(ValueError, match="Disposable Windows CI"):
        client_module["run"](*([tmp_path] * 7), {}, "not-a-password", {})
    assert list(tmp_path.rglob("*")) == before


def test_packet_checker_requires_native_and_helper_operations_and_no_unchanged_payload(
    tmp_path, client_module
):
    import zipfile

    base, target = tmp_path / "base", tmp_path / "target"
    base.mkdir()
    target.mkdir()
    old = [
        dict(path=n, sha256="a" * 64, size=100)
        for n in ("native/pdf/bin/pango-1.0-0.dll", "vira-updater.exe", "python/python.exe")
    ]
    new = copy.deepcopy(old)
    new[0]["sha256"] = new[1]["sha256"] = "b" * 64
    for root, files in ((base, old), (target, new)):
        (root / "install_manifest.json").write_text(json.dumps(dict(files=files)))

    def packet(extra=None, drop=None):
        out = tmp_path / "opaque.zip"
        ops = [dict(path=f["path"], op="replace") for f in new[:2] if f["path"] != drop]
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("update.json", json.dumps(dict(operations=ops)))
            for op in ops:
                z.writestr("files/" + op["path"], b"OPAQUE NOT EXECUTABLE")
            if extra:
                z.writestr(extra, b"NEVER EXECUTED")
        return out

    proof = client_module["check_packet"](base, target, packet())
    assert proof["unchanged_payload_files_absent"] and proof["full_installer_in_package"] is False
    for extra in ("files/python/python.exe", "VIRA-Setup.exe"):
        with pytest.raises(ValueError):
            client_module["check_packet"](base, target, packet(extra))
    with pytest.raises(ValueError):
        client_module["check_packet"](base, target, packet(drop="vira-updater.exe"))


def test_failure_diagnostics_collect_only_fixed_owned_bounded_startup_logs(tmp_path, client_module):
    home = tmp_path / "profile/VIRA/private-native-installed"
    updates = home / "state/data/updates"
    stage = updates / "99.30.1" / ("b" * 32)
    stage.mkdir(parents=True)
    reports = tmp_path / "reports"
    reports.mkdir()
    nonce = "c" * 32
    attempt = tmp_path / ("VIRA تراکنش خصوصی ! & " + nonce)
    attempt.mkdir()
    context = dict(role="PRIVATE_SOURCE_TRANSACTION", attempt=str(attempt))
    (stage / ("private-transaction-" + nonce + ".json")).write_text(json.dumps(context))
    data = b"SYNTHETIC STARTUP DIAGNOSTIC\n" * 1000
    (attempt / "target-startup.log").write_bytes(data)
    (attempt / "rollback-startup.log").write_bytes(b"rollback diagnostic")
    for secret in ("session.secret", "vira.sqlite3", "private-key.pem", "journal.json"):
        (attempt / secret).write_bytes(b"MUST NEVER BE COLLECTED")
    (home / ".native-update.lock").write_bytes(b"GUARD TOKEN MUST NEVER BE COLLECTED")
    before = {p: p.read_bytes() for p in attempt.iterdir()}
    client_module["collect_failure_diagnostics"](home, reports, tmp_path)
    out = reports / "failure-diagnostics"
    assert {p.name for p in out.iterdir()} == {
        "snapshot.json", nonce + "-target-startup.log", nonce + "-rollback-startup.log",
    }
    assert (out / (nonce + "-target-startup.log")).read_bytes() == data[-16384:]
    snapshot = json.loads((out / "snapshot.json").read_text())
    assert snapshot["guards_present"] == [False, True, False]
    assert snapshot["startup_logs"][0]["complete_bytes"] == len(data)
    assert before == {p: p.read_bytes() for p in attempt.iterdir()}
    assert (home / ".native-update.lock").read_bytes() == b"GUARD TOKEN MUST NEVER BE COLLECTED"


@pytest.mark.parametrize("fault", ["foreign-path", "invalid-nonce", "wrong-role"])
def test_failure_diagnostics_never_follow_unowned_contexts(tmp_path, client_module, fault):
    home = tmp_path / "profile/VIRA/private-native-installed"
    stage = home / "state/data/updates/99.30.1" / ("b" * 32)
    stage.mkdir(parents=True)
    reports = tmp_path / "reports"
    reports.mkdir()
    nonce = "c" * 32 if fault != "invalid-nonce" else "not-owned"
    attempt = tmp_path / ("VIRA تراکنش خصوصی ! & " + nonce)
    attempt.mkdir()
    (attempt / "target-startup.log").write_bytes(b"MUST NOT BE COLLECTED")
    value = dict(role="PRIVATE_SOURCE_TRANSACTION", attempt=str(attempt))
    if fault == "foreign-path":
        value["attempt"] = str(tmp_path / "foreign")
    if fault == "wrong-role":
        value["role"] = "FOREIGN"
    (stage / ("private-transaction-" + nonce + ".json")).write_text(json.dumps(value))
    client_module["collect_failure_diagnostics"](home, reports, tmp_path)
    out = reports / "failure-diagnostics"
    assert {p.name for p in out.iterdir()} == {"snapshot.json"}
    assert json.loads((out / "snapshot.json").read_text())["startup_logs"] == []

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


@pytest.mark.parametrize("status,body,headers,expected", [
    (503, {"code":"update_in_progress"}, {"Retry-After":"3"}, True),
    (422, {"detail":"invalid synthetic request"}, {}, False),
    (503, {"code":"other"}, {"Retry-After":"3"}, None),
    (503, {"code":"update_in_progress"}, {}, None),
    (200, {}, {}, None), (401, {}, {}, None),
])
def test_live_quarantine_protocol_never_infers_success_from_other_statuses(
    client_module, status, body, headers, expected
):
    def handler(request):
        assert request.method == "POST" and request.url.path == "/api/v1/orders"
        assert json.loads(request.content) == {}  # Invalid, never creates an order.
        return httpx.Response(status, json=body, headers=headers)
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://synthetic.test") as client:
        if expected is None:
            with pytest.raises(ValueError):
                client_module["probe_write_quarantine"](client)
        else:
            assert client_module["probe_write_quarantine"](client) is expected


@pytest.mark.parametrize("fault", [None, "source-drift", "extra", "wrong-pin", "existing", "symlink", "copy-drift"])
def test_old_external_recovery_clone_is_verified_before_any_execution(
    tmp_path, monkeypatch, client_module, fault
):
    """Opaque bytes ONLY: clone integrity, never executable/native acceptance."""
    root, destination = tmp_path / "installed", tmp_path / "external"
    root.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    contents = {"python/python.exe": b"OPAQUE NOT EXECUTABLE",
        "python/python311.zip": b"OPAQUE NOT STDLIB",
        "python/DLLs/fake.pyd": b"OPAQUE NOT A DLL",
        "scripts/private_source_update.py": b"OPAQUE NOT PYTHON"}
    for name, data in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    doc = json.dumps(dict(files=[dict(path=n, size=len(b), sha256=hashlib.sha256(b).hexdigest())
        for n,b in contents.items()])).encode()
    (root / "install_manifest.json").write_bytes(doc)
    pin = hashlib.sha256(doc).hexdigest()
    if fault == "source-drift":
        (root / "python/python.exe").write_bytes(b"DRIFT")
    elif fault == "extra":
        (root / "python/.hidden").write_bytes(b"UNOWNED")
    elif fault == "wrong-pin":
        pin = "0" * 64
    elif fault == "existing":
        destination.mkdir()
    elif fault == "symlink":
        (root / "python/alias").symlink_to(root / "python/DLLs", target_is_directory=True)
    elif fault == "copy-drift":
        scope = client_module["clone_recovery_runtime"].__globals__
        original = scope["shutil"].copytree
        def corrupt_copy(*args, **kwargs):
            result = original(*args, **kwargs)
            (destination / "python/python.exe").write_bytes(b"COPY DRIFT")
            return result
        monkeypatch.setattr(scope["shutil"], "copytree", corrupt_copy)
    if fault:
        with pytest.raises((ValueError, FileExistsError)):
            client_module["clone_recovery_runtime"](root, destination, pin)
    else:
        proof = client_module["clone_recovery_runtime"](root, destination, pin)
        assert proof == dict(controller_sha256=hashlib.sha256(contents["scripts/private_source_update.py"]).hexdigest(),
            python_file_count=3, old_manifest_sha256=pin)
        assert (destination / "scripts/private_source_update.py").read_bytes() == b"OPAQUE NOT PYTHON"
        (root / "scripts/private_source_update.py").write_bytes(b"REPLACED TARGET")
        assert (destination / "scripts/private_source_update.py").read_bytes() == b"OPAQUE NOT PYTHON"
        assert client_module["verify_recovery_runtime"](destination, pin) == proof
        (destination / "python/python.exe").write_bytes(b"LATER CLONE DRIFT")
        with pytest.raises(ValueError, match="runtime differs"):
            client_module["verify_recovery_runtime"](destination, pin)


@pytest.fixture
def cold_protocol(tmp_path, monkeypatch, client_module):
    """All metadata/process handles/HTTP SYNTHETIC; never a Windows crash proof."""
    from types import SimpleNamespace

    root = tmp_path / "installed"
    root.mkdir()
    home = tmp_path / "profile/VIRA/private-native-installed"
    stage = home / "state/data/updates/99.30.2/payload"
    stage.mkdir(parents=True)
    attempt = tmp_path / ("VIRA تراکنش خصوصی ! & " + "a" * 32)
    attempt.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    token = "e" * 64
    def write(path, doc):
        path.write_text(json.dumps(doc), encoding="utf-8")
    context = dict(role="PRIVATE_SOURCE_TRANSACTION", attempt=str(attempt),
        archive=str(stage.parent / "package.zip"), archive_sha256="b" * 64)
    context_path = stage.parent / ("private-transaction-" + "a" * 32 + ".json")
    write(context_path, context)
    owner = dict(pid=321, token=token)
    cut = dict(role="PRIVATE_CONTROLLER_ABRUPT_EXIT_73", point="FIRST_FILE", pid=321,
        applied_file_count=1, guard_token_sha256=hashlib.sha256(token.encode()).hexdigest())
    journal = dict(state="prepared", old_anchor_sha256="c" * 64, archive_sha256="b" * 64,
        database_fingerprint="d" * 64, recovery_context=dict(install_root=str(root)), changed=["one","two"])
    write(attempt / "process-cut.json", cut)
    write(attempt / "journal.json", journal)
    write(home / ".native-update.lock", owner)
    (stage.parent.parent / ".update.lock").write_bytes(token.encode())
    write(stage.parent.parent / "last-result.json", dict(attempt_id=attempt.name, state="failed", controller_exit_code=73, helper_pid=654))
    calls = []
    def dead(pid):
        calls.append(pid)
        return True
    scope = client_module["wait_cold_cut"].__globals__
    monkeypatch.setitem(scope, "process_definitely_dead", dead)
    return SimpleNamespace(root=root, home=home, stage=stage, attempt=attempt, context=context,
        context_path=context_path, cut=cut, journal=journal, write=write, calls=calls,
        scope=scope, args=(home, stage, root, "b" * 64, "c" * 64, "d" * 64, "FIRST_FILE"))


@pytest.mark.parametrize("fault", [None, "context", "archive", "counter", "old-pin", "db-pin", "journal", "token"])
def test_cold_cut_observer_requires_exact_authority_and_both_dead_handles(
    cold_protocol, client_module, fault
):
    r = cold_protocol
    if fault == "context":
        r.context["attempt"] = str(r.root)
        r.write(r.context_path, r.context)
    elif fault == "archive":
        r.context["archive_sha256"] = "0" * 64
        r.write(r.context_path, r.context)
    elif fault in {"counter", "token"}:
        r.cut["applied_file_count" if fault == "counter" else "guard_token_sha256"] = 9
        r.write(r.attempt / "process-cut.json", r.cut)
    elif fault in {"old-pin", "db-pin", "journal"}:
        key = {"old-pin":"old_anchor_sha256", "db-pin":"database_fingerprint", "journal":"state"}[fault]
        r.journal[key] = "WRONG"
        r.write(r.attempt / "journal.json", r.journal)
    with httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(503, json={"code":"update_in_progress"}, headers={"Retry-After":"3"})),
        base_url="http://synthetic.test") as client:
        if fault:
            with pytest.raises(ValueError):
                client_module["wait_cold_cut"](client, *r.args)
            assert not r.calls
        else:
            proof, saw_gate = client_module["wait_cold_cut"](client, *r.args)
            assert saw_gate and proof["controller_and_helper_handles_confirmed_dead"]
            assert r.calls == [321, 654] and proof["controller_exit_code"] == 73
            assert (r.home / ".native-update.lock").exists()
            assert (r.home / "state/data/updates/.update.lock").exists()


def test_cold_cut_observer_never_ages_out_or_deletes_a_live_guard(cold_protocol, client_module, monkeypatch):
    from types import SimpleNamespace

    r = cold_protocol
    monkeypatch.setitem(r.scope, "process_definitely_dead", lambda pid: False)
    ticks = iter([0,0,999])
    monkeypatch.setitem(r.scope, "time", SimpleNamespace(monotonic=lambda:next(ticks), sleep=lambda _:None))
    before = (r.home / ".native-update.lock").read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(422, json={})),
        base_url="http://synthetic.test") as client, pytest.raises(TimeoutError):
        client_module["wait_cold_cut"](client, *r.args)
    assert (r.home / ".native-update.lock").read_bytes() == before
    assert (r.home / "state/data/updates/.update.lock").exists()


def test_main_gate_has_one_integrated_cold_workflow_with_stock_and_source_coverage():
    import yaml

    # BaseLoader avoids interpreting GitHub's YAML 'on' key as a boolean.
    integrated = yaml.load((ROOT / ".github/workflows/pdf-desktop-source.yml").read_text(), Loader=yaml.BaseLoader)
    for event in ("push", "pull_request"):
        paths = integrated["on"][event]["paths"]
        assert "backend/app/main.py" in paths and "scripts/private_source_update.py" in paths
        for name in ("pdf-source-http.yml", "pdf-app-owned-http.yml"):
            standalone = yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)
            assert "backend/app/main.py" not in standalone["on"][event]["paths"]
            assert ".github/workflows/" + name not in standalone["on"][event]["paths"]
            assert "workflow_dispatch" in standalone["on"]
    script = (ROOT / ".github/workflows/pdf-desktop-source.yml").read_text()
    assert "pdf_bootstrap_sdk_smoke.ps1" in script and "pdf_source_http_bind.py" in script
    assert "pdf_owned_http_bind.py" in script and "phase3_installed_smoke.ps1" in script

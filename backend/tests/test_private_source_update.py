"""Synthetic byte/transaction-preflight tests, NOT Windows/DLL/Inno execution."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import zipfile
from pathlib import Path

import bsdiff4
import pytest

from app import private_installed_source as bridge
from app.services.update_engine import build_manifest, manifest_to_json, plan_delta

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))


def raw(value):
    return json.dumps(value, indent=2, ensure_ascii=False).encode()


def fixture(tmp_path, with_controller=False):
    base = tmp_path / "base"
    base.mkdir()
    before = {
        "version.json": raw({"version": "99.30.0", "spa_build": "old"}),
        "app/main.py": b"# synthetic, never executed\n",
        "native/pdf/bin/pango.dll": b"OPAQUE SYNTHETIC NOT A DLL\n" * 1000,
        "python/python.exe": b"OPAQUE SYNTHETIC NOT AN INTERPRETER\n" * 100,
        "static/deleted.txt": b"old deletion restored on rollback",
        "static/edit.txt": b"old",
    }
    if with_controller:
        before["app/private_installed_source.py"] = (
            ROOT / "backend/app/private_installed_source.py"
        ).read_bytes()
        before["scripts/update_database.py"] = (ROOT / "scripts/update_database.py").read_bytes()
    after = dict(before)
    after["version.json"] = raw({"version": "99.30.1", "spa_build": "new"})
    after["native/pdf/bin/pango.dll"] += b"synthetic changed native-directory bytes"
    after["static/edit.txt"] = b"new"
    del after["static/deleted.txt"]
    after["static/added.txt"] = b"added"
    target_dir = tmp_path / "target-input"
    for directory, files in [(base, before), (target_dir, after)]:
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    bm, tm = build_manifest(base), build_manifest(target_dir)
    old_raw, target_raw = raw(manifest_to_json(bm)), raw(manifest_to_json(tm))
    (base / "install_manifest.json").write_bytes(old_raw)
    plan, members = plan_delta("99.30.0", "99.30.1", bm, tm, patch_threshold=128)
    contents = {"install_manifest.json": target_raw, "version.json": after["version.json"]}
    hashes = {}
    for name, (kind, relative) in members.items():
        data = (
            bsdiff4.diff(before[relative], after[relative])
            if kind.value == "patch"
            else after[relative]
        )
        contents[name] = data
        hashes[name] = hashlib.sha256(data).hexdigest()
    doc = plan.to_json()
    doc["hashes"] = hashes
    contents["update.json"] = raw(doc)
    contents["delete.json"] = raw({"deleted": ["static/deleted.txt"]})
    return (
        base,
        before,
        after,
        contents,
        {"manifest_sha256": hashlib.sha256(old_raw).hexdigest()},
        {"manifest_sha256": hashlib.sha256(target_raw).hexdigest()},
    )


def packet(tmp_path, contents):
    path = tmp_path / "delta.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    return path


def assemble(tmp_path, base, contents, old, target):
    archive = packet(tmp_path, contents)
    return MODULE["assemble"](
        base, archive, tmp_path / "assembled", old, target, MODULE["sha"](archive)
    )


def test_lossless_changed_parts_native_directory_patch_and_complete_target(tmp_path):
    base, before, after, contents, old, target = fixture(tmp_path)
    bm, tm, changed = assemble(tmp_path, base, contents, old, target)
    assert set(bm) == set(before) and set(tm) == set(after)
    assert "python/python.exe" not in changed
    assert "patches/native/pdf/bin/pango.dll.bsdiff" in contents
    assert not any("python.exe" in name for name in contents)
    assert all((tmp_path / "assembled" / name).read_bytes() == data for name, data in after.items())
    assert all((base / name).read_bytes() == data for name, data in before.items())


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-member",
        "traversal",
        "case-collision",
        "missing-member",
        "member-hash",
        "missing-hash",
        "extra-op",
        "missing-op",
        "wrong-kind",
        "op-hash",
        "op-size",
        "wrong-base-version",
        "wrong-target-version",
        "target-manifest",
        "base-bytes",
        "base-extra",
        "patch-header",
        "patch-path",
        "duplicate-json",
        "opaque-data-target",
    ],
)
def test_preflight_tampering_never_changes_installed_baseline(tmp_path, mutation):
    base, before, _, contents, old, target = fixture(tmp_path)
    doc = json.loads(contents["update.json"])
    name = next(n for n in contents if n.startswith("files/"))
    if mutation == "extra-member":
        contents["unexpected.exe"] = b"never executed"
    elif mutation == "traversal":
        contents["files/app/../../data/vira.sqlite3"] = b"no"
    elif mutation == "case-collision":
        contents[name.upper()] = contents[name]
    elif mutation == "missing-member":
        del contents[name]
    elif mutation == "member-hash":
        contents[name] += b"corrupt"
    elif mutation == "missing-hash":
        del doc["hashes"][name]
    elif mutation == "extra-op":
        doc["operations"].append(copy.deepcopy(doc["operations"][0]))
    elif mutation == "missing-op":
        doc["operations"].pop()
    elif mutation == "wrong-kind":
        doc["operations"][0]["op"] = "exec"
    elif mutation == "op-hash":
        next(o for o in doc["operations"] if o["op"] != "delete")["sha256"] = "0" * 64
    elif mutation == "op-size":
        next(o for o in doc["operations"] if o["op"] != "delete")["size"] = -1
    elif mutation == "wrong-base-version":
        doc["base_version"] = "99.0.0"
    elif mutation == "wrong-target-version":
        doc["target_version"] = "99.0.0"
    elif mutation == "target-manifest":
        contents["install_manifest.json"] += b" "
    elif mutation == "base-bytes":
        (base / "app/main.py").write_bytes(b"preexisting corruption")
    elif mutation == "base-extra":
        (base / "unexpected.py").write_bytes(b"preexisting unmanifested")
    elif mutation == "patch-header":
        member = next(n for n in contents if n.startswith("patches/"))
        contents[member] = b"invalid"
        doc["hashes"][member] = hashlib.sha256(contents[member]).hexdigest()
    elif mutation == "patch-path":
        next(o for o in doc["operations"] if o["op"] == "patch")["patch"] = (
            "patches/app/../bad.bsdiff"
        )
    elif mutation == "opaque-data-target":
        doc["operations"][0]["path"] = "data/vira.sqlite3"
    if mutation == "duplicate-json":
        contents["update.json"] = b'{"operations":[],"operations":[]}'
    else:
        contents["update.json"] = raw(doc)
    baseline = {
        p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()
    }
    with pytest.raises((ValueError, KeyError)):
        assemble(tmp_path, base, contents, old, target)
    assert baseline == {
        p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "path",
    [
        "../app/x",
        "/app/x",
        "app/../x",
        "app/./x",
        "app//x",
        "app/x.",
        "app/x ",
        "app/NUL.txt",
        "app/COM1",
        "app/x:y",
        "app\\x",
        "data/vira.sqlite3",
        "native/other/x",
        "app/*",
        "app/x\x00",
    ],
)
def test_windows_path_aliases_and_business_paths_rejected(path):
    with pytest.raises(ValueError):
        MODULE["relative"](path)


def test_external_sha_and_symlinks_rejected_without_mutation(tmp_path):
    base, _, _, contents, old, target = fixture(tmp_path)
    archive = packet(tmp_path, contents)
    with pytest.raises(ValueError, match="External archive"):
        MODULE["assemble"](base, archive, tmp_path / "out", old, target, "0" * 64)
    source = base / "app/main.py"
    original = tmp_path / "original.py"
    source.rename(original)
    source.symlink_to(original)
    with pytest.raises(ValueError, match="reparse/symlink"):
        assemble(tmp_path, base, contents, old, target)


def test_manifest_case_alias_and_boolean_size_rejected(tmp_path):
    base, _, _, _, old, _ = fixture(tmp_path)
    doc = json.loads((base / "install_manifest.json").read_bytes())
    for change in ("case", "bool"):
        value = copy.deepcopy(doc)
        if change == "case":
            value["files"].append(dict(value["files"][0], path=value["files"][0]["path"].upper()))
        else:
            value["files"][0]["size"] = True
        data = raw(value)
        with pytest.raises(ValueError):
            MODULE["manifest"](data, hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError):
        MODULE["manifest"](raw(doc), "0" * 64)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"", b""),
        (b"", b"new"),
        (b"old", b""),
        (bytes(range(256)) * 50, bytes(range(255, -1, -1)) * 48),
    ],
    ids=["empty", "insert", "delete", "binary-12kb"],
)
def test_bounded_stdlib_patch_matches_actual_bsdiff4(old, new):
    assert MODULE["patch"](old, bsdiff4.diff(old, new), len(new)) == new


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", True),
        ("role", "PUBLIC"),
        ("port", True),
        ("port", 0),
        ("no_browser", 1),
        ("manifest_sha256", "A" * 64),
        ("source_audit_sha256", None),
    ],
)
def test_installed_anchor_strict_schema(key, value):
    doc = dict(
        schema=1,
        role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
        manifest_sha256="a" * 64,
        inventory_sha256="b" * 64,
        source_audit_sha256="c" * 64,
        port=8787,
        no_browser=True,
    )
    assert bridge.anchor(doc) == doc
    doc[key] = value
    with pytest.raises(ValueError):
        bridge.anchor(doc)


def test_no_duplicate_anchor_or_public_profile(tmp_path, monkeypatch):
    path = tmp_path / "anchor.json"
    path.write_bytes(b'{"role":"a","role":"b"}')
    with pytest.raises(ValueError):
        bridge.read(path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "outside"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    with pytest.raises(ValueError):
        bridge.location()


def test_patch_decompression_budget_and_invalid_header():
    with pytest.raises(ValueError):
        MODULE["patch"](b"", b"BSDIFF40" + b"\xff" * 24, 0)
    with pytest.raises(ValueError):
        MODULE["patch"](b"", b"not a patch", 0)


def test_imports_are_stdlib_only_and_no_native_or_installer_claim():
    for path in (
        ROOT / "scripts/private_source_update.py",
        ROOT / "backend/app/private_installed_source.py",
    ):
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(n, ast.ImportFrom) and n.module and n.module.startswith(("app.", "scripts."))
            for n in ast.walk(tree)
        )
    assert "Synthetic" in __doc__


@pytest.mark.parametrize(
    "mode",
    [
        "commit",
        "force-after-apply",
        "target-start-failure",
        "rollback-start-failure",
        "preflight-failure",
        "commit-receipt-failure",
        "rollback-receipt-failure",
        "crash-first-file-denied",
        "crash-after-apply-denied",
    ],
)
def test_synthetic_transaction_with_real_sqlite_snapshot_restore(tmp_path, monkeypatch, mode):
    """Mock process boundaries, real files/ZIP/BSDIFF/SQLite. NOT native proof."""
    import os
    import sqlite3
    import subprocess
    import sys
    from contextlib import closing
    from types import SimpleNamespace

    base, before, after, contents, old, target = fixture(tmp_path, with_controller=True)
    archive = packet(tmp_path, contents)
    home = tmp_path / "کاربر فارسی ! & profile" / "VIRA/private-native-installed"
    home.mkdir(parents=True)
    state = home / "state"
    state.mkdir()
    (state / "private-desktop-state.json").write_bytes(
        raw(dict(schema=1, role="PRIVATE_SOURCE_DESKTOP_STATE", payload_root=str(base)))
    )
    receipts = state / "data/receipts/immutable.bin"
    receipts.parent.mkdir(parents=True)
    receipts.write_bytes(b"preserve all receipt bytes")
    secret = state / "session.secret"
    secret.write_bytes(b"synthetic persistent session secret, not a real credential")
    database = state / "data/data/vira.sqlite3"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('synthetic-0006'); CREATE TABLE posted(id TEXT PRIMARY KEY, amount INTEGER); INSERT INTO posted VALUES('original-id',1234567891234);"
        )
    common = dict(
        schema=1,
        role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
        inventory_sha256="b" * 64,
        source_audit_sha256="c" * 64,
        port=8787,
        no_browser=True,
    )
    old = dict(common, **old)
    target = dict(common, **target)
    old_bytes = raw(old)
    (home / "anchor.json").write_bytes(old_bytes)
    target_pin = tmp_path / "target-anchor.json"
    target_pin.write_bytes(raw(target))
    attempt = tmp_path / "attempt"
    controller = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))["main"]
    scope = controller.__globals__
    fake_os = SimpleNamespace(
        name="nt",
        environ=dict(
            os.environ,
            GITHUB_ACTIONS="true",
            RUNNER_TEMP=str(tmp_path),
            LOCALAPPDATA=str(home.parents[1]),
        ),
        getpid=os.getpid,
        fsync=os.fsync,
    )
    monkeypatch.setitem(scope, "os", fake_os)
    preflight_calls = []
    starts = []
    original_atomic = scope["atomic"]
    def atomic_mock(path, data):
        if path == attempt / "result.json":
            state_name = json.loads(data)["state"]
            if (mode == "commit-receipt-failure" and state_name == "committed"
                    or mode == "rollback-receipt-failure" and state_name == "rolled_back"):
                raise OSError("synthetic durable receipt write failure")
        return original_atomic(path, data)
    monkeypatch.setitem(scope, "atomic", atomic_mock)

    def preflight(command, **kwargs):
        assert command[1:6] == ["-I", "-S", "-B", "-X", "utf8"]
        assert kwargs["cwd"] == home
        preflight_calls.append(command)
        if mode == "preflight-failure":
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setitem(scope, "subprocess", SimpleNamespace(run=preflight))

    def start_mock(_home, root, token, pin, log):
        assert log.parent == attempt and log.name in {"target-startup.log", "rollback-startup.log"}
        assert len(token) == 64 and _home == home
        assert (home / "state/data/updates/.update.lock").read_bytes() == token.encode()
        starts.append(pin["manifest_sha256"])
        assert scope["sha"](root / "install_manifest.json") == pin["manifest_sha256"]
        if mode in {"target-start-failure", "rollback-start-failure"} and len(starts) == 1:
            # Simulate failed target migration/writer, not app/renderer injection.
            with closing(sqlite3.connect(database)) as db, db:
                db.execute("UPDATE posted SET amount=-1")
                db.execute("CREATE TABLE failed_target_only(value TEXT)")
            raise RuntimeError("synthetic failed target startup")
        if mode == "rollback-start-failure":
            raise RuntimeError("synthetic rollback health failure")
        return object()

    monkeypatch.setitem(scope, "start", start_mock)
    args = [
        "private-controller",
        "--install-root",
        str(base),
        "--archive",
        str(archive),
        "--archive-sha256",
        MODULE["sha"](archive),
        "--target-anchor",
        str(target_pin),
        "--attempt",
        str(attempt),
    ]
    if mode in {"force-after-apply", "rollback-receipt-failure"}:
        args.append("--force-failure-after-apply")
    if mode.startswith("crash-"):
        args += ["--crash-point", "FIRST_FILE" if mode == "crash-first-file-denied" else "AFTER_APPLY"]
        monkeypatch.setattr(sys, "argv", args)
        with pytest.raises(ValueError, match="schema2 private CI"):
            controller()
        assert not attempt.exists() and not preflight_calls and not starts
        assert all((base / name).read_bytes() == data for name, data in before.items())
        assert (home / "anchor.json").read_bytes() == old_bytes
        assert not (home / ".native-update.lock").exists()
        assert not (home / "state/data/updates/.update.lock").exists()
        return
    monkeypatch.setattr(sys, "argv", args)
    if mode == "commit":
        controller()
    else:
        with pytest.raises((RuntimeError, OSError, subprocess.CalledProcessError)):
            controller()
    assert len(preflight_calls) == 1
    expected = after if mode == "commit" else before
    assert all((base / name).read_bytes() == data for name, data in expected.items())
    assert receipts.read_bytes() == b"preserve all receipt bytes"
    assert secret.read_bytes() == b"synthetic persistent session secret, not a real credential"
    with closing(sqlite3.connect(database)) as db, db:
        assert db.execute("SELECT * FROM posted").fetchall() == [("original-id", 1234567891234)]
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name='failed_target_only'"
        ).fetchall()
    assert (home / "anchor.json").read_bytes() == (raw(target) if mode == "commit" else old_bytes)
    if mode in {"rollback-start-failure", "rollback-receipt-failure"}:
        assert (home / "state/data/updates/.update.lock").is_file()
        assert (home / ".native-update.lock").exists()  # fail CLOSED, retain recovery evidence
        assert not (attempt / "result.json").exists()  # no false rolled_back success
    else:
        assert not (home / "state/data/updates/.update.lock").exists()
        assert not (home / ".native-update.lock").exists()
        if mode != "preflight-failure":
            result = json.loads((attempt / "result.json").read_bytes())
            assert result["state"] == ("committed" if mode == "commit" else "rolled_back")
    if mode in {"target-start-failure", "rollback-start-failure"}:
        assert (attempt / "database-rollback/failed-database/database.sqlite3").exists()


def test_owned_atomic_temporary_is_removed_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "target.txt"
    target.write_bytes(b"original")

    def fail(*args):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        MODULE["atomic"](target, b"new")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_rejected_target_preserves_startup_diagnostics_without_overwriting(tmp_path, monkeypatch):
    """Mock owned child only; actual exclusive file/stream handling, no native proof."""
    from types import SimpleNamespace

    start = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))["start"]
    scope = start.__globals__
    home, root = tmp_path / "home", tmp_path / "payload"
    home.mkdir()
    root.mkdir()
    log = tmp_path / "target-startup.log"
    calls, streams = [], []

    class Child:
        pid = 123456

        def poll(self):
            return 9

        def wait(self, timeout):
            assert timeout == 15
            return 9

    def spawn(argv, **kwargs):
        assert argv[-1] == str(root / "app/private_installed_source.py")
        assert kwargs["env"]["VIRA_PRIVATE_UPDATE_TOKEN"] == "a" * 64
        assert kwargs["stderr"] == -2  # subprocess.STDOUT, not discarded.
        calls.append(argv)
        streams.append(kwargs["stdout"])
        kwargs["stdout"].write(b"VIRA private desktop startup rejected: NATIVE_MODULE_ABSENT\n")
        kwargs["stdout"].flush()
        return Child()

    def reap(argv, **kwargs):
        assert argv == ["taskkill", "/PID", "123456", "/T", "/F"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setitem(scope, "subprocess", SimpleNamespace(Popen=spawn, STDOUT=-2, run=reap))
    with pytest.raises(RuntimeError, match="exited before readiness"):
        start(home, root, "a" * 64, {"port": 8787}, log)
    expected = b"VIRA private desktop startup rejected: NATIVE_MODULE_ABSENT\n"
    assert log.read_bytes() == expected and streams[0].closed
    with pytest.raises(FileExistsError):
        start(home, root, "a" * 64, {"port": 8787}, log)
    assert len(calls) == 1 and log.read_bytes() == expected


@pytest.mark.parametrize("point", ["FIRST_FILE", "AFTER_APPLY"])
def test_actual_checkpoint_exit_bypasses_finally_but_is_not_windows_native_proof(tmp_path, point):
    """Actual os._exit, SIMULATED Windows/CI gate; no executable/DLL/app fixture."""
    import subprocess
    import sys

    attempt = tmp_path / "attempt"
    attempt.mkdir()
    marker = tmp_path / "finally-must-not-run"
    token = "e" * 64
    code = f"""
import os, runpy
from pathlib import Path
from types import SimpleNamespace
m = runpy.run_path({str(ROOT / 'scripts/private_source_update.py')!r})
f = m['crash_checkpoint']
f.__globals__['os'] = SimpleNamespace(name='nt', environ={{'GITHUB_ACTIONS':'true'}},
    getpid=os.getpid, fsync=os.fsync, _exit=os._exit)
try:
    f({point!r}, {point!r}, Path({str(attempt)!r}), {token!r}, 1)
finally:
    Path({str(marker)!r}).write_text('THIS MUST NOT HAPPEN')
"""
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code], capture_output=True, timeout=15)
    assert child.returncode == 73, child.stderr.decode()
    assert not marker.exists()
    receipt = json.loads((attempt / "process-cut.json").read_bytes())
    assert receipt == dict(role="PRIVATE_CONTROLLER_ABRUPT_EXIT_73", point=point,
        pid=receipt["pid"], applied_file_count=1,
        guard_token_sha256=hashlib.sha256(token.encode()).hexdigest())
    assert token not in json.dumps(receipt) and receipt["pid"] > 0


@pytest.mark.parametrize("platform,ci", [("posix", "true"), ("nt", "false"), ("nt", "")])
def test_checkpoint_denies_nonprivate_environment_without_writing(tmp_path, monkeypatch, platform, ci):
    from types import SimpleNamespace

    checkpoint = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))["crash_checkpoint"]
    monkeypatch.setitem(checkpoint.__globals__, "os", SimpleNamespace(name=platform, environ={"GITHUB_ACTIONS": ci}))
    with pytest.raises(ValueError, match="private Windows"):
        checkpoint("FIRST_FILE", "FIRST_FILE", tmp_path, "e" * 64, 1)
    assert not list(tmp_path.iterdir())


def test_unselected_checkpoint_is_a_pure_noop_without_platform_override(tmp_path):
    MODULE["crash_checkpoint"](None, "FIRST_FILE", tmp_path, "e" * 64, 1)
    assert not list(tmp_path.iterdir())

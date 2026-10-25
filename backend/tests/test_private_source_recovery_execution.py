"""Recovery writes use real files/ZIP/SQLite; app startup is mocked, NOT native acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager

import pytest

from .test_private_source_recovery_inspection import recovery as recovery
from .test_private_source_recovery_inspection import tree_bytes
from .test_private_source_update import ROOT, raw


@pytest.fixture
def executor(recovery, monkeypatch):
    r = recovery
    scope = r.inspect.__globals__
    monkeypatch.setattr(scope["os"], "fsync", os.fsync, raising=False)
    monkeypatch.setattr(scope["os"], "getpid", os.getpid, raising=False)
    held, starts, stops = [], [], []

    @contextmanager
    def mutex():
        assert not held
        held.append(True)
        try:
            yield
        finally:
            held.clear()

    original_inspect = r.inspect

    def inspect(*args):
        assert held, "No eligibility inspection outside the global mutex"
        return original_inspect(*args)

    def start(home, root, token, options, log):
        assert held and token == "d" * 64
        assert home == r.home and root == r.root
        assert options["version"] == "99.30.0"
        assert log.parent == r.attempt and log.name.startswith("recovery-startup-")
        assert r.guard.read_bytes() == token.encode()
        assert (home / ".native-update.lock").exists()
        starts.append((home, root))
        return object()  # Explicit fake readiness boundary, NEVER executable/native proof.

    def stop(home, root):
        assert held and starts and (home, root) == starts[-1]
        stops.append((home, root))

    monkeypatch.setitem(scope, "recovery_mutex", mutex)
    monkeypatch.setitem(scope, "inspect_recovery", inspect)
    monkeypatch.setitem(scope, "start", start)
    monkeypatch.setitem(scope, "stop", stop)
    r.execute = scope["recover"]
    r.scope, r.held, r.starts, r.stops = scope, held, starts, stops
    return r


def test_recovery_restores_partial_old_tree_database_ids_and_assets_before_unlock(executor):
    r = executor
    secret = (r.home / "state/session.secret").read_bytes()
    receipt = (r.home / "state/data/receipts/preserve.bin").read_bytes()
    backup_before = tree_bytes(r.bundle)
    with closing(sqlite3.connect(r.database)) as db, db:
        db.execute("UPDATE posted SET amount=-123")
        db.execute("CREATE TABLE failed_target_only(value TEXT)")
    result = r.execute(*r.args)
    assert result["recovery_executed"] and result["locks_released"]
    assert not result["crash_recovery_proven"] and not result["release_authorized"]
    assert not r.guard.exists() and not (r.home / ".native-update.lock").exists()
    old_raw = (r.attempt / "anchor-before.json").read_bytes()
    assert (r.home / "anchor.json").read_bytes() == old_raw
    baseline = r.scope["manifest"](
        (r.root / "install_manifest.json").read_bytes(), json.loads(old_raw)["manifest_sha256"]
    )
    r.scope["verify"](r.root, baseline)
    assert (r.home / "state/session.secret").read_bytes() == secret
    assert (r.home / "state/data/receipts/preserve.bin").read_bytes() == receipt
    with closing(sqlite3.connect(r.database)) as db:
        assert db.execute("SELECT * FROM posted").fetchall() == [("same-id", 12345678901000)]
        assert db.execute("SELECT name FROM sqlite_master WHERE name='failed_target_only'").fetchall() == []
    assert (r.bundle / "database.sqlite3").read_bytes() == backup_before["database.sqlite3"]
    assert (r.bundle / "failed-database/database.sqlite3").is_file()
    terminal = json.loads((r.home / "state/data/updates/last-result.json").read_bytes())
    assert terminal["state"] == "rolled_back" and terminal["recovery_verified"]
    assert terminal["verified"] is False and terminal["attempt_id"] == r.attempt.name
    assert json.loads((r.attempt / "result.json").read_bytes())["state"] == "rolled_back"
    assert len(r.starts) == 1 and not r.stops and not r.held
    assert "d" * 64 not in json.dumps(result) + json.dumps(terminal)


@pytest.mark.parametrize("fault", ["live-pid", "channel", "desktop", "archive", "backup", "guard-owner", "terminal"])
def test_recovery_ineligible_inputs_never_write_or_release(executor, monkeypatch, fault):
    r = executor
    if fault == "live-pid":
        monkeypatch.setitem(r.scope, "process_definitely_dead", lambda _: False)
    elif fault in {"channel", "desktop", "terminal"}:
        path = {"channel": r.home / ".native-channel.lock",
                "desktop": r.home / "state/.desktop.lock",
                "terminal": r.attempt / "result.json"}[fault]
        path.write_bytes(b"never remove an unknown or terminal guard")
    elif fault == "archive":
        r.archive.write_bytes(b"not authorized")
    elif fault == "backup":
        (r.attempt / "files-before/static/edit.txt").write_bytes(b"corrupt")
    else:
        r.guard.write_bytes(b"foreign owner")
    before = tree_bytes(r.tmp)
    with pytest.raises(ValueError):
        r.execute(*r.args)
    assert tree_bytes(r.tmp) == before and not r.starts and not r.held


def test_recovery_busy_mutex_never_inspects_or_writes(executor, monkeypatch):
    @contextmanager
    def busy():
        raise RuntimeError("Another updater owns the global mutex")
        yield  # pragma: no cover

    monkeypatch.setitem(executor.scope, "recovery_mutex", busy)
    before = tree_bytes(executor.tmp)
    with pytest.raises(RuntimeError, match="global mutex"):
        executor.execute(*executor.args)
    assert tree_bytes(executor.tmp) == before and not executor.starts


def test_recovery_revalidates_after_acquiring_mutex_and_before_writes(executor, monkeypatch):
    r = executor
    real_inspect = r.scope["inspect_recovery"]
    changed = []

    def race(*args):
        result = real_inspect(*args)
        r.guard.write_bytes(b"foreign owner appeared after inspection")
        changed.append(tree_bytes(r.tmp))
        return result

    monkeypatch.setitem(r.scope, "inspect_recovery", race)
    with pytest.raises(ValueError):
        r.execute(*r.args)
    assert tree_bytes(r.tmp) == changed[0] and not r.starts


@pytest.mark.parametrize("fault", ["startup", "database-after-start", "result-publication", "guard-during-publication"])
def test_recovery_failure_never_unlocks_or_claims_success(executor, monkeypatch, fault):
    r = executor
    original_start, original_atomic = r.scope["start"], r.scope["atomic"]

    def start(*args):
        if fault == "startup":
            raise RuntimeError("synthetic rejected restart")
        result = original_start(*args)
        if fault == "database-after-start":
            with closing(sqlite3.connect(r.database)) as db, db:
                db.execute("UPDATE posted SET amount=-1")
        return result

    def atomic(path, data):
        if path == r.attempt / "result.json":
            if fault == "result-publication":
                raise OSError("synthetic durable receipt failure")
            if fault == "guard-during-publication":
                r.guard.write_bytes(b"FOREIGN guard, must never delete")
        original_atomic(path, data)

    monkeypatch.setitem(r.scope, "start", start)
    monkeypatch.setitem(r.scope, "atomic", atomic)
    with pytest.raises((RuntimeError, ValueError, OSError)):
        r.execute(*r.args)
    assert r.guard.exists() and (r.home / ".native-update.lock").exists()
    assert not r.held
    if fault == "guard-during-publication":
        assert r.guard.read_bytes() == b"FOREIGN guard, must never delete"
    if fault != "startup":
        assert len(r.stops) == 1  # Only the app THIS executor restarted.
    if fault in {"startup", "database-after-start", "result-publication"}:
        assert not (r.attempt / "result.json").exists()


def test_windows_global_mutex_is_shared_across_actual_owned_processes():
    module = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))
    mutex = module["recovery_mutex"]
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        with pytest.raises(ValueError, match="Windows CI recovery"), mutex():
            pytest.fail("No non-Windows recovery activation")
        return  # Platform rejection is exercised, not skipped/native acceptance.
    script = (
        "import runpy,sys; "
        f"m=runpy.run_path({str(ROOT / 'scripts/private_source_update.py')!r}); "
        "ctx=m['recovery_mutex'](); "
        "\ntry:\n ctx.__enter__()\nexcept RuntimeError:\n sys.exit(23)\n"
        "ctx.__exit__(None,None,None)\n"
    )
    with mutex():
        blocked = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script], capture_output=True, timeout=15)
        assert blocked.returncode == 23, blocked.stderr.decode(errors="replace")
    admitted = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script], capture_output=True, timeout=15)
    assert admitted.returncode == 0, admitted.stderr.decode(errors="replace")


def test_windows_abrupt_owned_child_cut_restores_real_sqlite_and_files(executor, monkeypatch):
    """Real Windows child os._exit + mutex + restore; app readiness still FAKE."""
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        assert executor.scope["os"].name == "nt"  # Fixture remains explicitly simulated.
        return
    r = executor
    script = (
        "import os,json,sqlite3,hashlib; from pathlib import Path; "
        f"home=Path({str(r.home)!r}); attempt=Path({str(r.attempt)!r}); "
        "p=home/'.native-update.lock'; lock=json.loads(p.read_bytes()); lock['pid']=os.getpid(); "
        "p.write_text(json.dumps(lock)); "
        "p=attempt/'journal.json'; j=json.loads(p.read_bytes()); "
        "j['recovery_context']['controller_pid']=os.getpid(); p.write_text(json.dumps(j)); "
        f"db=sqlite3.connect({str(r.database)!r}); "
        "db.execute('UPDATE posted SET amount=-999'); db.commit(); db.close(); os._exit(73)"
    )
    child = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script], capture_output=True, timeout=15)
    assert child.returncode == 73, child.stderr.decode(errors="replace")
    real = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))
    monkeypatch.setitem(r.scope, "process_definitely_dead", real["process_definitely_dead"])
    monkeypatch.setitem(r.scope, "recovery_mutex", real["recovery_mutex"])
    # Keep the fixture's assertion that all mutations happen under the mutex.
    original_start = r.scope["start"]

    def owned_ready(*args):
        r.held.append(True)
        try:
            return original_start(*args)
        finally:
            r.held.clear()

    monkeypatch.setitem(r.scope, "start", owned_ready)
    monkeypatch.setitem(r.scope, "inspect_recovery", r.inspect)
    result = r.execute(*r.args)
    assert result["recovery_executed"] and not result["crash_recovery_proven"]
    with closing(sqlite3.connect(r.database)) as db:
        assert db.execute("SELECT * FROM posted").fetchall() == [("same-id", 12345678901000)]
    assert hashlib.sha256((r.attempt / "anchor-before.json").read_bytes()).hexdigest() == r.args[-2]


def test_recovery_rejects_database_metadata_race_before_any_restore(executor, monkeypatch):
    r = executor
    original_atomic = r.scope["atomic"]
    before = r.database.read_bytes()
    foreign = r.tmp / "MUST-NOT-BE-CREATED.sqlite3"

    def atomic(path, data):
        original_atomic(path, data)
        if path == r.home / "anchor.json":
            meta = json.loads((r.bundle / "metadata.json").read_bytes())
            meta["database"] = str(foreign)
            (r.bundle / "metadata.json").write_bytes(raw(meta))

    monkeypatch.setitem(r.scope, "atomic", atomic)
    with pytest.raises(ValueError, match="snapshot changed before restore"):
        r.execute(*r.args)
    assert not foreign.exists() and r.database.read_bytes() == before
    assert r.guard.exists() and not r.starts


@pytest.mark.parametrize("extra", [[], ["--old-anchor-sha256", "a" * 64], ["--force-failure-after-apply"]])
def test_recovery_cli_never_infers_missing_independent_authority(tmp_path, monkeypatch, extra):
    module = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))
    monkeypatch.setattr(sys, "argv", [
        "controller", "--recover", "--install-root", str(tmp_path),
        "--attempt", str(tmp_path), "--archive", str(tmp_path / "opaque.zip"),
        "--archive-sha256", "b" * 64, *extra,
    ])
    before = tree_bytes(tmp_path)
    with pytest.raises(SystemExit) as error:
        module["main"]()
    assert error.value.code == 2 and tree_bytes(tmp_path) == before


def test_successful_recovery_cannot_be_replayed(executor):
    r = executor
    r.execute(*r.args)
    before = tree_bytes(r.tmp)
    with pytest.raises(ValueError, match="terminal transaction"):
        r.execute(*r.args)
    assert tree_bytes(r.tmp) == before and len(r.starts) == 1


def test_second_guard_unlink_io_failure_restores_owned_write_guard(executor, monkeypatch):
    from pathlib import Path

    r = executor
    original = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == r.home / ".native-update.lock":
            raise OSError("synthetic second unlink I/O failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(OSError, match="second unlink"):
        r.execute(*r.args)
    assert r.guard.read_bytes() == b"d" * 64
    assert (r.home / ".native-update.lock").exists() and len(r.stops) == 1

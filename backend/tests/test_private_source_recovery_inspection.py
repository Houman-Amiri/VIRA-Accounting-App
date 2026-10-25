"""Read-only cold recovery eligibility, NOT recovery/native/crash acceptance.

Files, ZIP, SHA and SQLite are real; app/native processes remain opaque. A separate
Windows branch queries actual owned interpreter handles without executing payloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from types import SimpleNamespace

import pytest

from .test_private_source_update import ROOT, fixture, packet, raw


def tree_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    module = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))
    base, before, after, contents, old, target = fixture(tmp_path, with_controller=True)
    common = dict(
        schema=2,
        role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
        inventory_sha256="b" * 64,
        source_audit_sha256="c" * 64,
        port=8787,
        no_browser=True,
    )
    old = dict(common, **old, version="99.30.0")
    target = dict(common, **target, version="99.30.1")
    contents["private-source-anchor.json"] = raw(target)
    archive = packet(tmp_path, contents)
    home = tmp_path / "profile فارسی ! &" / "VIRA/private-native-installed"
    state = home / "state"
    state.mkdir(parents=True)
    (state / "private-desktop-state.json").write_bytes(
        raw(dict(schema=1, role="PRIVATE_SOURCE_DESKTOP_STATE", payload_root=str(base)))
    )
    (home / "anchor.json").write_bytes(raw(target))
    (state / "session.secret").write_bytes(b"OPAQUE persistent secret, NOT a credential")
    receipt = state / "data/receipts/preserve.bin"
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b"accounting receipt must never be modified by inspection")
    database = state / "data/data/vira.sqlite3"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript(
            "CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('synthetic'); CREATE TABLE posted(id TEXT PRIMARY KEY, amount INTEGER); INSERT INTO posted VALUES('same-id',12345678901000);"
        )
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    dbtool = runpy.run_path(str(ROOT / "scripts/update_database.py"))
    snapshot = dbtool["snapshot"](database, attempt / "database-rollback")
    baseline = module["manifest"](
        (base / "install_manifest.json").read_bytes(), old["manifest_sha256"]
    )
    final = module["manifest"](contents["install_manifest.json"], target["manifest_sha256"])
    changed = sorted(n for n in set(baseline) | set(final) if baseline.get(n) != final.get(n))
    backup = attempt / "files-before"
    for n in changed + ["install_manifest.json"]:
        if (base / n).exists():
            p = backup / n
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / n, p)
    (attempt / "anchor-before.json").write_bytes(raw(old))
    token = "d" * 64
    (home / ".native-update.lock").write_bytes(raw(dict(token=token, pid=424242)))
    guard = state / "data/updates/.update.lock"
    guard.parent.mkdir(parents=True)
    guard.write_bytes(token.encode())
    journal = dict(
        schema=1,
        role="PRIVATE_NATIVE_TRANSACTION_JOURNAL",
        state="prepared",
        changed=changed,
        archive_sha256=module["sha"](archive),
        old_anchor_sha256=hashlib.sha256(raw(old)).hexdigest(),
        target_anchor_sha256=hashlib.sha256(raw(target)).hexdigest(),
        database_fingerprint=snapshot["fingerprint"],
        recovery_context=dict(
            install_root=str(base),
            home=str(home),
            controller_pid=424242,
            guard_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        ),
    )
    (attempt / "journal.json").write_bytes(raw(journal))
    # A genuinely PARTIALLY applied file tree must not be assumed fully old/new.
    (base / "static/edit.txt").write_bytes(after["static/edit.txt"])
    (base / "native/pdf/bin/pango.dll").unlink()
    inspect = module["inspect_recovery"]
    monkeypatch.setitem(
        inspect.__globals__,
        "os",
        SimpleNamespace(
            name="nt",
            environ=dict(
                os.environ,
                GITHUB_ACTIONS="true",
                RUNNER_TEMP=str(tmp_path),
                LOCALAPPDATA=str(home.parents[1]),
            ),
        ),
    )
    monkeypatch.setitem(inspect.__globals__, "process_definitely_dead", lambda pid: pid == 424242)
    args = [
        base,
        home,
        attempt,
        archive,
        module["sha"](archive),
        journal["old_anchor_sha256"],
        snapshot["fingerprint"],
    ]
    return SimpleNamespace(
        inspect=inspect,
        args=args,
        home=home,
        attempt=attempt,
        root=base,
        archive=archive,
        journal=journal,
        database=database,
        bundle=attempt / "database-rollback",
        guard=guard,
        tmp=tmp_path,
    )


def test_valid_cold_prepared_inspection_never_restores_or_unlinks(recovery):
    before = tree_bytes(recovery.tmp)
    result = recovery.inspect(*recovery.args)
    assert result["eligible_for_offline_recovery"] is True
    assert all(
        result[k] is False
        for k in (
            "recovery_executed",
            "locks_released",
            "authorization_reusable",
            "crash_recovery_proven",
            "phase3_complete",
            "release_authorized",
        )
    )
    assert tree_bytes(recovery.tmp) == before
    assert recovery.guard.exists() and (recovery.home / ".native-update.lock").exists()
    assert not (recovery.root / "native/pdf/bin/pango.dll").exists()
    assert "d" * 64 not in json.dumps(result)


@pytest.mark.parametrize(
    "mutation",
    [
        "live-pid",
        "unknown-pid",
        "pid-reused-during-read",
        "pid-bool",
        "channel",
        "desktop",
        "active",
        "terminal",
        "write-owner",
        "journal-owner",
        "journal-state",
        "journal-bool-schema",
        "changed-set",
        "old-anchor",
        "current-anchor",
        "manifest",
        "backup-file",
        "missing-backup",
        "extra-backup",
        "archive",
        "database-path",
        "database-schema-bool",
        "database-bytes",
        "database-logical-data",
        "old-db-tool",
        "unchanged-file",
        "missing-unchanged-file",
        "extra-root-file",
        "db-authority",
        "not-ci",
    ],
)
def test_ineligible_recovery_fails_without_any_cleanup_or_data_change(
    recovery, monkeypatch, mutation
):
    r = recovery
    scope = r.inspect.__globals__
    if mutation == "live-pid":
        monkeypatch.setitem(scope, "process_definitely_dead", lambda _: False)
    elif mutation == "unknown-pid":

        def unknown(_):
            raise RuntimeError("synthetic inaccessible Windows handle")

        monkeypatch.setitem(scope, "process_definitely_dead", unknown)
    elif mutation == "pid-reused-during-read":
        states = iter([True, False])
        monkeypatch.setitem(scope, "process_definitely_dead", lambda _: next(states))
    elif mutation == "pid-bool":
        (r.home / ".native-update.lock").write_bytes(raw(dict(token="d" * 64, pid=True)))
    elif mutation in {"channel", "desktop", "active", "terminal"}:
        p = {
            "channel": r.home / ".native-channel.lock",
            "desktop": r.home / "state/.desktop.lock",
            "active": r.home / "active-launch.json",
            "terminal": r.attempt / "result.json",
        }[mutation]
        p.write_bytes(b"foreign or live or terminal - never erase")
    elif mutation == "write-owner":
        r.guard.write_bytes(b"foreign")
    elif mutation in {"journal-owner", "journal-state", "journal-bool-schema", "changed-set"}:
        if mutation == "journal-owner":
            r.journal["recovery_context"]["home"] = "foreign"
        if mutation == "journal-state":
            r.journal["state"] = "committed"
        if mutation == "journal-bool-schema":
            r.journal["schema"] = True
        if mutation == "changed-set":
            r.journal["changed"] = []
        (r.attempt / "journal.json").write_bytes(raw(r.journal))
    elif mutation == "old-anchor":
        (r.attempt / "anchor-before.json").write_bytes(b"{}")
    elif mutation == "current-anchor":
        (r.home / "anchor.json").write_bytes(b"{}")
    elif mutation == "manifest":
        (r.attempt / "files-before/install_manifest.json").write_bytes(b"{}")
    elif mutation == "backup-file":
        (r.attempt / "files-before/static/edit.txt").write_bytes(b"bad")
    elif mutation == "missing-backup":
        (r.attempt / "files-before/static/edit.txt").unlink()
    elif mutation == "extra-backup":
        (r.attempt / "files-before/unknown.txt").write_bytes(b"unknown")
    elif mutation == "archive":
        r.archive.write_bytes(b"bad ZIP, reject by external hash before parsing")
    elif mutation in {"database-path", "database-schema-bool"}:
        p = r.bundle / "metadata.json"
        meta = json.loads(p.read_bytes())
        if mutation == "database-path":
            meta["database"] = str(r.tmp / "foreign.sqlite3")
        else:
            meta["schema_version"] = True
        p.write_bytes(raw(meta))
    elif mutation == "database-bytes":
        (r.bundle / "database.sqlite3").write_bytes(b"bad")
    elif mutation == "database-logical-data":
        p = r.bundle / "database.sqlite3"
        with closing(sqlite3.connect(p)) as db, db:
            db.execute("UPDATE posted SET amount=amount+1")
        meta = json.loads((r.bundle / "metadata.json").read_bytes())
        meta["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        (r.bundle / "metadata.json").write_bytes(raw(meta))
    elif mutation == "old-db-tool":
        (r.root / "scripts/update_database.py").write_bytes(
            b'raise AssertionError("MUST NEVER EXECUTE")'
        )
    elif mutation == "unchanged-file":
        (r.root / "python/python.exe").write_bytes(b"CORRUPT OPAQUE FILE")
    elif mutation == "missing-unchanged-file":
        (r.root / "python/python.exe").unlink()
    elif mutation == "extra-root-file":
        (r.root / "unknown-atomic-debris").write_bytes(b"do not erase")
    elif mutation == "db-authority":
        r.args[-1] = "0" * 64
    elif mutation == "not-ci":
        scope["os"].environ["GITHUB_ACTIONS"] = "false"
    before = tree_bytes(r.tmp)
    with pytest.raises((ValueError, RuntimeError)):
        r.inspect(*r.args)
    assert tree_bytes(r.tmp) == before
    assert r.guard.exists() and (r.home / ".native-update.lock").exists()


def test_recovery_pin_reparse_is_rejected_even_with_identical_bytes(recovery):
    pin = recovery.home / "anchor.json"
    target = recovery.tmp / "same-anchor.json"
    target.write_bytes(pin.read_bytes())
    pin.unlink()
    pin.symlink_to(target)
    with pytest.raises(ValueError, match="reparse/symlink"):
        recovery.inspect(*recovery.args)
    assert pin.is_symlink() and recovery.guard.exists()


def test_process_handle_query_refuses_live_and_accepts_exited_owned_child_only():
    module = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))
    query = module["process_definitely_dead"]
    if sys.platform != "win32":
        with pytest.raises(ValueError, match="Windows process handles"):
            query(os.getpid())
        return  # Platform rejection is tested, NOT skipped/native acceptance.
    assert query(os.getpid()) is False
    child = subprocess.Popen(
        [sys.executable, "-I", "-S", "-B", "-c", "import time; time.sleep(60)"]
    )
    try:
        assert query(child.pid) is False
    finally:
        child.terminate()  # Only the process THIS control created.
        child.wait(timeout=15)
    assert query(child.pid) is True
    for invalid in (True, 0, -1, 2**32):
        with pytest.raises(ValueError):
            query(invalid)

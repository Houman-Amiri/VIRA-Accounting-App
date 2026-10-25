"""Read-only receipt replay, NOT another Windows/native execution."""

from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIND = runpy.run_path(str(ROOT / "scripts/phase3_installed_bind.py"))["validate"]
WITNESS = json.loads(
    (ROOT / "docs/dependencies/phase3-installed-source21-evidence.json").read_bytes()
)


def test_authenticated_recovered_installed_witness_consistency():
    assert BIND(copy.deepcopy(WITNESS)) == WITNESS


@pytest.mark.parametrize(
    "path,value",
    [
        ("role", "OPAQUE_INNO_SMOKE"),
        ("phase3_complete", True),
        ("native_delta_rollback_proven", True),
        ("release_authorized", True),
        ("persistent_session_secret_preserved", False),
        ("anchor.schema", 1),
        ("anchor.version", "99.30.1"),
        ("anchor.source_audit_sha256", "0" * 64),
        ("native_audit.native_compilation", "FAILED"),
        ("cases.first-installed-process.completed.qa_worker_executed", True),
        ("cases.first-installed-process.completed.qa_factory_or_renderer_replacement", True),
        ("cases.first-installed-process.completed.desktop_lock_released", False),
        ("cases.first-installed-process.completed.bootstrap_temp_cleaned", False),
        ("cases.first-installed-process.completed.graceful_shutdown", False),
        ("cases.first-installed-process.completed.activation.dll_count", 27),
        ("cases.first-installed-process.completed.activation.windows_acp", 1252),
        ("cases.first-installed-process.completed.activation.manifest_sha256", "0" * 64),
        ("cases.first-installed-process.completed.loaded_dlls.ffi-8.dll", "C:/foreign/ffi-8.dll"),
        ("cases.first-installed-process.ready.url", "http://127.0.0.1:1"),
        ("cases.first-installed-process.ready.browser_opened", True),
        ("cases.first-installed-process.http.missing_csrf_rejected", False),
        ("cases.first-installed-process.http.transport", "ASGI_TRANSPORT"),
        ("cases.first-installed-process.documents.multi-page.pages", 1),
        ("cases.first-installed-process.documents.single-page.sha256", "0" * 64),
        (
            "cases.restarted-installed-process.http.prior_process_session_accepted_before_new_login",
            False,
        ),
        ("cases.restarted-installed-process.http.fixture_ids.single-page", "different-id"),
        ("cases.restarted-installed-process.ready.database", "C:/foreign/data.sqlite3"),
    ],
)
def test_recovered_installed_witness_tampering_rejected(path, value):
    # DLL/file names contain dots; use the remaining full suffix when it is a key.
    w = copy.deepcopy(WITNESS)
    target, rest = w, path
    while rest not in target:
        key, rest = rest.split(".", 1)
        target = target[key]
    target[rest] = value
    with pytest.raises(ValueError):
        BIND(w)


def test_restart_pid_must_be_fresh():
    w = copy.deepcopy(WITNESS)
    first, again = w["cases"].values()
    for obj in (again["ready"], again["completed"], again["completed"]["activation"]):
        obj["pid"] = first["ready"]["pid"]
    with pytest.raises(ValueError, match="restart identity"):
        BIND(w)


def test_document_resource_isolation_is_rechecked():
    w = copy.deepcopy(WITNESS)
    fonts = w["cases"]["first-installed-process"]["font_documents"]
    fonts[1]["font_folder"] = fonts[0]["font_folder"]
    with pytest.raises(ValueError, match="isolation"):
        BIND(w)

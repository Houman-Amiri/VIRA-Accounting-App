"""Replay authenticated Windows Phase 2 witness; replay itself is not native execution."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
from pathlib import Path, PureWindowsPath

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs/dependencies"


def recorded(tmp_path):
    raw = (DATA / "pdf-desktop-source-http-evidence.json").read_bytes()
    proof = json.loads((DATA / "pdf-desktop-source-http-proof.json").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == proof["witness"]["sha256"]
    assert len(raw) == proof["witness"]["bytes"]
    witness = json.loads(raw)
    audit = tmp_path / "audit.json"
    audit.write_bytes((json.dumps(witness["native_audit"], indent=2) + "\n").encode())
    assert hashlib.sha256(audit.read_bytes()).hexdigest() == witness["native_audit_sha256"]
    validate = runpy.run_path(str(ROOT / "scripts/desktop_launcher_bind.py"))["validate"]
    return witness, proof, audit, validate


def test_authenticated_real_cmd_windows_witness_and_frozen_code(tmp_path):
    witness, proof, audit, validate = recorded(tmp_path)
    assert validate(witness, audit) == witness
    assert proof["workflow_run"]["conclusion"] == "success"
    assert all(job["conclusion"] == "success" for job in proof["all_jobs"])
    assert proof["workflow_run"]["path"] == ".github/workflows/pdf-desktop-source.yml"
    assert proof["artifact_zip_independently_downloaded_or_hashed"] is True
    assert proof["local_artifact_zip_downloaded"] is False
    recovery = proof["lossless_recovery"]
    assert recovery["workflow_run"]["conclusion"] == "success"
    assert len(recovery["checks"]) == 8
    assert {v["provenance"]["group"] for v in recovery["checks"]} == set(range(8))
    assert all(
        v["conclusion"] == "success"
        and v["provenance"]["witness_sha256"] == proof["witness"]["sha256"]
        and v["provenance"]["artifact_id"] == proof["artifact"]["id"]
        and "sha256:" + v["provenance"]["downloaded_zip_sha256"] == proof["artifact"]["digest"]
        and v["provenance"]["application_reexecuted"] is False
        for v in recovery["checks"]
    )
    assert proof["all_six_distribution_gates_still_open"] is True
    # Phase3 extends the private modules, write gate and workflow. Retain exact OLD bytes rather than
    # rewriting historical proof hashes or claiming old Windows evidence for new code.
    extended = {"backend/app/private_pdf_bootstrap.py", "backend/app/desktop_entry.py", "backend/app/main.py", ".github/workflows/pdf-desktop-source.yml"}
    for name, digest in proof["frozen_implementation_git_blob_sha256"].items():
        source = (DATA / "phase2-frozen-implementation" / Path(name).name) if name in extended else ROOT / name
        assert hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
    for case in witness["cases"].values():
        completed = case["completed"]
        native = PureWindowsPath(completed["activation"]["libffi"])
        assert native.name == "ffi-8.dll"
        assert native == PureWindowsPath(completed["loaded_dlls"]["ffi-8.dll"])
        assert tuple(native.parent.parts[-3:]) == ("native", "pdf", "bin")
        assert all(
            PureWindowsPath(path).parent == native.parent
            for path in completed["loaded_dlls"].values()
        )
    assert (
        witness["cases"]["restarted-process"]["http"][
            "prior_process_session_accepted_before_new_login"
        ]
        is True
    )
    assert all(
        v["pre_native_and_pre_app_rejection"] is True for v in witness["negative_controls"].values()
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "role",
        "release",
        "default",
        "audit",
        "pid",
        "acp",
        "qa",
        "renderer",
        "dll-count",
        "dll-set",
        "secret",
        "old-session",
        "seed",
        "browser",
        "pdf",
        "system-font",
        "cleanup",
        "restart-pid",
        "database",
        "fixtures",
        "negative",
        "negative-native",
        "manifest",
        "workspace",
    ],
)
def test_recorded_real_cmd_witness_rejects_tampering(tmp_path, mutation):
    original, _, audit, validate = recorded(tmp_path)
    result = copy.deepcopy(original)
    first = result["cases"]["first-process"]
    again = result["cases"]["restarted-process"]
    if mutation == "role":
        result["role"] = "ORDINARY_RELEASE"
    elif mutation == "release":
        result["release_authorized"] = True
    elif mutation == "default":
        result["ordinary_default_enabled"] = True
    elif mutation == "audit":
        result["native_audit_sha256"] = "0" * 64
    elif mutation == "pid":
        first["ready"]["pid"] += 1
    elif mutation == "acp":
        first["completed"]["activation"]["windows_acp"] = 1252
    elif mutation == "qa":
        first["completed"]["qa_worker_executed"] = True
    elif mutation == "renderer":
        first["completed"]["renderer_module"] = "qa.renderer"
    elif mutation == "dll-count":
        first["completed"]["activation"]["dll_count"] = 27
    elif mutation == "dll-set":
        first["completed"]["loaded_dlls"].pop("ffi-8.dll")
    elif mutation == "secret":
        again["persistent_secret_preserved"] = False
    elif mutation == "old-session":
        again["http"]["prior_process_session_accepted_before_new_login"] = False
    elif mutation == "seed":
        again["completed"]["seed"]["users_created"] = 1
    elif mutation == "browser":
        first["ready"]["browser_opened"] = True
    elif mutation == "pdf":
        first["documents"]["single-page"]["sha256"] = "0" * 64
    elif mutation == "system-font":
        first["font_documents"][0]["system_fonts"] = 1
    elif mutation == "cleanup":
        first["font_documents"][0]["cache_temp_cleaned"] = False
    elif mutation == "restart-pid":
        for target in (again["ready"], again["completed"], again["completed"]["activation"]):
            target["pid"] = first["ready"]["pid"]
    elif mutation == "database":
        again["ready"]["database"] = again["completed"]["database"] = "other.db"
    elif mutation == "fixtures":
        again["http"]["fixture_ids"]["single-page"] = "other-id"
    elif mutation == "negative":
        result["negative_controls"]["update-lock"]["exit_code"] = 0
    elif mutation == "negative-native":
        result["negative_controls"]["duplicate-instance"]["pre_native_and_pre_app_rejection"] = (
            False
        )
    elif mutation == "manifest":
        first["completed"]["activation"]["manifest_sha256"] = "0" * 64
    elif mutation == "workspace":
        again["completed"]["activation"]["bootstrap_temp"] = first["completed"]["activation"][
            "bootstrap_temp"
        ]
    with pytest.raises((ValueError, KeyError)):
        validate(result, audit)


def test_default_cmd_body_still_matches_phase1_baseline():
    cmd = (ROOT / "scripts/start_vira.cmd").read_text(encoding="utf-8")
    cmd = cmd[: cmd.index("\n:private_source_candidate\n")]
    start = cmd.index("REM Explicit private source")
    end = cmd.index('cd /d "%~dp0"', start)
    original_body = cmd[:start] + cmd[end:]
    assert (
        hashlib.sha256(original_body.encode("utf-8")).hexdigest()
        == "a385c16ae8eaf49a61b06f8016fc1b22deaa000bcb3bc01554b9ad8eb0229cf4"
    )

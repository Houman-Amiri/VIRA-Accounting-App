"""Opaque report-content controls only: NO authenticated/native process proof."""
from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts/authenticate_controller_crash.py"))


@pytest.fixture
def report():
    doc = dict(role="PHASE3_REAL_IN_APP_SOURCE21_NATIVE_DELTA_AND_FORCED_ROLLBACK_PRIVATE_NOT_RELEASE",
        real_native_delta_and_forced_rollback=True, crash_recovery_proven=True,
        live_write_quarantine_verified=True, full_setup_requested=False, phase3_complete=False,
        release_authorized=False, crash_scope=MODULE["SCOPE"], power_loss_or_arbitrary_cut_proven=False,
        crash_during_recovery_or_partial_terminal_unlock_auto_resumable=False,
        baseline_audit_sha256="a" * 64, target_audit_sha256="b" * 64, cases={})
    for name, point in MODULE["CASES"].items():
        state = "committed" if name == "commit" else "rolled_back"
        case = dict(terminal=dict(state=state, verified=name == "commit"),
            journal=dict(state=state, database_fingerprint="c" * 64),
            database_fingerprint_before="c" * 64, database_fingerprint_after="c" * 64,
            old_pid=10, new_pid=20, write_quarantine_http503_observed=True,
            completed=dict(loaded_dlls={str(n):"OPAQUE NOT A DLL" for n in range(21)},
                activation=dict(dll_count=21, source_audit_sha256="b" * 64), pango_version="1.58.0-vira-local-source"),
            package=dict(changed=["OPAQUE"] * 25, native_operations=["OPAQUE"] * 21,
                unchanged_payload_files_absent=True, full_installer_in_package=False),
            documents={str(n):"OPAQUE NOT A PDF" for n in range(4)},
            crash_recovery_proven=point is not None, crash=None, recovery_executor=None, old_external_recovery_clone=None,
            **dict.fromkeys(MODULE["PRESERVED"], True))
        if point:
            case["journal"]["recovery_verified"] = True
            case["crash"] = dict(controller_exit_code=73, controller_and_helper_handles_confirmed_dead=True,
                cut=dict(role="PRIVATE_CONTROLLER_ABRUPT_EXIT_73", point=point,
                         applied_file_count=1 if point == "FIRST_FILE" else 25))
            case["old_external_recovery_clone"] = dict(controller_sha256="d" * 64, old_manifest_sha256="e" * 64, python_file_count=2)
            case["recovery_executor"] = dict(role="PRIVATE_PREPARED_RECOVERY_EXECUTED_NOT_CRASH_ACCEPTANCE",
                recovery_executed=True, restored_old_tree=True, app_ready_verified=True,
                session_and_receipts_preserved=True, locks_released=True,
                database_fingerprint="c" * 64, crash_recovery_proven=False, phase3_complete=False, release_authorized=False)
        doc["cases"][name] = case
    return doc


def test_validated_content_never_claims_github_authentication_and_drops_paths(report):
    report["cases"]["crash-first-file"]["secret-must-not-copy"] = "SENSITIVE SYNTHETIC VALUE"
    summary = MODULE["summarize"](report)
    assert summary["role"] == "VALIDATED_REPORT_CONTENT_NOT_GITHUB_AUTHENTICATED"
    assert summary["phase3_complete"] is False and summary["release_authorized"] is False
    assert "SENSITIVE" not in json.dumps(summary) and "OPAQUE" not in json.dumps(summary)
    assert all(c["pdf_document_count"] == 4 and c["loaded_dll_count"] == 21 for c in summary["cases"].values())
    assert summary["cases"]["crash-first-file"]["cut"]["applied_file_count"] == 1
    assert summary["cases"]["crash-after-apply"]["cut"]["applied_file_count"] == 25


@pytest.mark.parametrize("case", MODULE["CASES"])
@pytest.mark.parametrize("field", [*MODULE["PRESERVED"], "write_quarantine_http503_observed"])
def test_every_case_must_preserve_every_asset_and_observe_actual_503(report, case, field):
    report["cases"][case][field] = False
    with pytest.raises(ValueError, match="Preservation"):
        MODULE["summarize"](report)


@pytest.mark.parametrize("field,value", [("crash_recovery_proven", False), ("live_write_quarantine_verified", False),
    ("power_loss_or_arbitrary_cut_proven", True), ("phase3_complete", True), ("release_authorized", True),
    ("full_setup_requested", True), ("crash_scope", "UNBOUNDED")])
def test_report_does_not_expand_its_proof_or_publication_scope(report, field, value):
    report[field] = value
    with pytest.raises(ValueError):
        MODULE["summarize"](report)


@pytest.mark.parametrize("fault", ["missing-case", "extra-case", "fingerprint", "native-count", "audit", "pdf-count", "unchanged", "full-setup"])
def test_content_validation_preserves_all_native_and_data_acceptance_gates(report, fault):
    case = report["cases"]["commit"]
    if fault == "missing-case":
        del report["cases"]["crash-after-apply"]
    elif fault == "extra-case":
        report["cases"]["UNPROVEN"] = copy.deepcopy(case)
    elif fault == "fingerprint":
        case["journal"]["database_fingerprint"] = "f" * 64
    elif fault == "native-count":
        case["completed"]["loaded_dlls"].pop("0")
    elif fault == "audit":
        case["completed"]["activation"]["source_audit_sha256"] = "f" * 64
    elif fault == "pdf-count":
        case["documents"].pop("0")
    elif fault == "unchanged":
        case["package"]["unchanged_payload_files_absent"] = False
    else:
        case["package"]["full_installer_in_package"] = True
    with pytest.raises(ValueError):
        MODULE["summarize"](report)


@pytest.mark.parametrize("fault", ["exit", "live-helper", "point", "counter", "clone", "clone-count", "recovery-data", "recovery-ready", "unlocked", "terminal"])
def test_both_actual_cut_and_limited_recovery_contract_are_required(report, fault):
    case = report["cases"]["crash-after-apply"]
    if fault == "exit":
        case["crash"]["controller_exit_code"] = 0
    elif fault == "live-helper":
        case["crash"]["controller_and_helper_handles_confirmed_dead"] = False
    elif fault == "point":
        case["crash"]["cut"]["point"] = "FIRST_FILE"
    elif fault == "counter":
        case["crash"]["cut"]["applied_file_count"] = 1
    elif fault == "clone":
        case["old_external_recovery_clone"]["controller_sha256"] = ""
    elif fault == "clone-count":
        case["old_external_recovery_clone"]["python_file_count"] = True
    elif fault == "recovery-data":
        case["recovery_executor"]["database_fingerprint"] = "f" * 64
    elif fault == "recovery-ready":
        case["recovery_executor"]["app_ready_verified"] = False
    elif fault == "unlocked":
        case["recovery_executor"]["locks_released"] = False
    else:
        case["journal"]["recovery_verified"] = False
    with pytest.raises(ValueError):
        MODULE["summarize"](report)


def test_historical_two_case_no_503_summary_is_not_upgraded_into_crash_proof():
    historical = json.loads((ROOT / "docs/dependencies/phase3-native-success-authenticated-summary.json").read_bytes())
    with pytest.raises(ValueError, match="role"):
        MODULE["summarize"](historical)


@pytest.mark.parametrize("pin", [{}, {"run": 40469951991}, dict(run=True, job=1, artifact=1, head="a"*40, sha256="b"*64, bytes=1)])
def test_authenticator_requires_complete_independent_pins_before_any_network_call(pin, monkeypatch):
    def forbidden(_):
        raise AssertionError("No network allowed for missing/invalid pins")
    monkeypatch.setitem(MODULE["authenticate"].__globals__, "api", forbidden)
    with pytest.raises(ValueError):
        MODULE["authenticate"](pin)


@pytest.mark.parametrize("fault", ["failed-run", "head", "failed-job", "step", "artifact-digest"])
def test_wrong_producer_or_artifact_stops_before_binary_download(monkeypatch, fault):
    pin = dict(run=40469951991, job=122075876445, artifact=1, head="a"*40, sha256="b"*64, bytes=100)
    run = dict(head_sha=pin["head"], conclusion="success", event="push",
               head_repository=dict(full_name=MODULE["REPO"]), path=".github/workflows/pdf-desktop-source.yml")
    job = dict(run_id=pin["run"], conclusion="success", steps=[dict(name=MODULE["STEP"], conclusion="success"),
        dict(name="Phase3 independently cold-build genuine native codegen target NOT delta acceptance", conclusion="success")])
    artifact = dict(workflow_run=dict(id=pin["run"], head_sha=pin["head"]), name=MODULE["ARTIFACT"], expired=False,
                    digest="sha256:"+pin["sha256"], size_in_bytes=100)
    if fault == "failed-run":
        run["conclusion"] = "failure"
    elif fault == "head":
        run["head_sha"] = "c" * 40
    elif fault == "failed-job":
        job["conclusion"] = "failure"
    elif fault == "step":
        job["steps"][0]["conclusion"] = "skipped"
    else:
        artifact["digest"] = "sha256:" + "c" * 64
    docs = {f"actions/runs/{pin['run']}":run, f"actions/jobs/{pin['job']}":job, "actions/artifacts/1":artifact}
    scope = MODULE["authenticate"].__globals__
    monkeypatch.setitem(scope, "api", lambda path:docs[path])
    def forbidden(*args, **kwargs):
        raise AssertionError("No binary download for an unauthenticated producer")
    monkeypatch.setattr(scope["subprocess"], "check_output", forbidden)
    with pytest.raises(ValueError):
        MODULE["authenticate"](pin)

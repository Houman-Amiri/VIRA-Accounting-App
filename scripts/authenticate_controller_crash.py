"""Read-only GitHub artifact authentication; never rebuild or execute an app.

A pinned producer must have completed BOTH independently built Source21 targets
and all four real transaction cases. Unit fixtures for the content validator are
not authenticated native evidence. No data, cookies, keys or raw logs are emitted.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import subprocess
import zipfile
import zlib
from pathlib import Path

REPO = "Houman-Amiri/VIRA-Accounting-App"
ARTIFACT = "private-phase3-native-delta-rollback-controller-cuts-no-app-db-dlls-NOT-release"
STEP = "Phase3 REAL native delta rollback two controller cuts and verified recovery with live HTTP503"
SCOPE = "controller_exit_73_after_first_file_and_after_file_apply_before_target_startup"
PRESERVED = ("full_database_preserved", "persistent_session_accepted_without_login",
             "persistent_secret_preserved", "receipt_bytes_preserved", "posted_entry_preserved")
CASES = {"commit": None, "rollback": None, "crash-first-file": "FIRST_FILE", "crash-after-apply": "AFTER_APPLY"}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def digest(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def summarize(doc: dict) -> dict:
    """Validate report content only; the caller must authenticate its provenance."""
    require(doc["role"] == "PHASE3_REAL_IN_APP_SOURCE21_NATIVE_DELTA_AND_FORCED_ROLLBACK_PRIVATE_NOT_RELEASE", "Report role differs")
    require(doc["real_native_delta_and_forced_rollback"] is True and doc["crash_recovery_proven"] is True
            and doc["live_write_quarantine_verified"] is True, "Native/crash/live503 acceptance missing")
    require(doc["full_setup_requested"] is False and doc["phase3_complete"] is False
            and doc["release_authorized"] is False, "Report exceeded private acceptance scope")
    require(doc["crash_scope"] == SCOPE and doc["power_loss_or_arbitrary_cut_proven"] is False
            and doc["crash_during_recovery_or_partial_terminal_unlock_auto_resumable"] is False, "Crash scope differs")
    require(set(doc["cases"]) == set(CASES), "Exactly four actual transaction cases required")
    require(digest(doc["baseline_audit_sha256"]) and digest(doc["target_audit_sha256"]), "Independent audits missing")
    result = dict(role="VALIDATED_REPORT_CONTENT_NOT_GITHUB_AUTHENTICATED", cases={}, crash_scope=SCOPE,
                  crash_recovery_proven=True, live_write_quarantine_verified=True,
                  power_loss_or_arbitrary_cut_proven=False, phase3_complete=False, release_authorized=False)
    for name, point in CASES.items():
        case = doc["cases"][name]
        expected = "committed" if name == "commit" else "rolled_back"
        require(case["terminal"]["state"] == case["journal"]["state"] == expected
                and case["terminal"]["verified"] is (name == "commit"), "Terminal receipt differs")
        fingerprint = case["database_fingerprint_before"]
        require(digest(fingerprint) and fingerprint == case["database_fingerprint_after"]
                == case["journal"]["database_fingerprint"], "Independent full database fingerprint differs")
        require(all(case[k] is True for k in PRESERVED) and case["write_quarantine_http503_observed"] is True,
                "Preservation or actual live503 missing")
        require(case["old_pid"] != case["new_pid"], "App process was not replaced")
        completed, packet = case["completed"], case["package"]
        require(len(completed["loaded_dlls"]) == completed["activation"]["dll_count"] == 21
                and completed["pango_version"] == "1.58.0-vira-local-source"
                and completed["activation"]["source_audit_sha256"] == doc["target_audit_sha256"], "Actual Source21 activation differs")
        require(packet["unchanged_payload_files_absent"] is True and packet["full_installer_in_package"] is False
                and len(packet["native_operations"]) == 21 and len(case["documents"]) == 4, "Native delta or real PDF coverage differs")
        require(case["crash_recovery_proven"] is (point is not None), "Case crash scope differs")
        cut_summary = None
        if point:
            crash, recovery, clone = case["crash"], case["recovery_executor"], case["old_external_recovery_clone"]
            cut = crash["cut"]
            count = cut["applied_file_count"]
            require(crash["controller_exit_code"] == 73 and crash["controller_and_helper_handles_confirmed_dead"] is True
                    and cut["role"] == "PRIVATE_CONTROLLER_ABRUPT_EXIT_73" and cut["point"] == point
                    and type(count) is int and count == (1 if point == "FIRST_FILE" else len(packet["changed"])), "Actual cold process cut differs")
            require(recovery["role"] == "PRIVATE_PREPARED_RECOVERY_EXECUTED_NOT_CRASH_ACCEPTANCE"
                    and all(recovery[k] is True for k in ("recovery_executed", "restored_old_tree", "app_ready_verified", "session_and_receipts_preserved", "locks_released"))
                    and recovery["database_fingerprint"] == fingerprint and recovery["crash_recovery_proven"] is False
                    and recovery["phase3_complete"] is False and recovery["release_authorized"] is False
                    and case["journal"]["recovery_verified"] is True, "Limited recovery executor contract differs")
            require(digest(clone["controller_sha256"]) and digest(clone["old_manifest_sha256"])
                    and type(clone["python_file_count"]) is int and clone["python_file_count"] > 0, "Independent old clone missing")
            cut_summary = dict(point=point, exit_code=73, applied_file_count=count,
                               controller_and_helper_confirmed_dead=True, independent_old_clone_verified=True,
                               old_controller_sha256=clone["controller_sha256"])
        else:
            require(all(case[k] is None for k in ("crash", "recovery_executor", "old_external_recovery_clone")), "Ordinary case contains a crash proof")
        result["cases"][name] = dict(state=expected, preserved={k: True for k in PRESERVED},
            database_fingerprint=fingerprint, write_quarantine_http503_observed=True,
            loaded_dll_count=21, native_operation_count=21, changed_file_count=len(packet["changed"]),
            pdf_document_count=4, unchanged_payload_files_absent=True, full_installer_in_package=False, cut=cut_summary)
    return result


def api(path: str) -> dict:
    return json.loads(subprocess.check_output(["gh", "api", f"repos/{REPO}/{path}"]))


def authenticate(pin: dict) -> dict:
    require(set(pin) == {"run", "job", "head", "artifact", "sha256", "bytes"}, "Exact independent producer pin required")
    require(all(type(pin[k]) is int and pin[k] > 0 for k in ("run", "job", "artifact", "bytes"))
            and 0 < pin["bytes"] <= 16 * 1024 * 1024 and digest(pin["sha256"])
            and isinstance(pin["head"], str) and re.fullmatch(r"[0-9a-f]{40}", pin["head"]) is not None, "Invalid producer identity")
    run, job = api(f"actions/runs/{pin['run']}"), api(f"actions/jobs/{pin['job']}")
    require(run["head_sha"] == pin["head"] and run["conclusion"] == "success"
            and run["event"] == "push" and run["head_repository"]["full_name"] == REPO
            and run["path"] == ".github/workflows/pdf-desktop-source.yml"
            and job["run_id"] == pin["run"] and job["conclusion"] == "success", "Producer did not pass at pinned revision")
    steps = {s["name"]: s["conclusion"] for s in job["steps"]}
    require(steps.get(STEP) == "success" and steps.get("Phase3 independently cold-build genuine native codegen target NOT delta acceptance") == "success", "Actual independent native/transaction step missing")
    artifact = api(f"actions/artifacts/{pin['artifact']}")
    require(artifact["workflow_run"]["id"] == pin["run"] and artifact["workflow_run"]["head_sha"] == pin["head"]
            and artifact["name"] == ARTIFACT and artifact["expired"] is False
            and artifact["digest"] == "sha256:" + pin["sha256"] and artifact["size_in_bytes"] == pin["bytes"], "Artifact metadata differs")
    raw = subprocess.check_output(["gh", "api", f"repos/{REPO}/actions/artifacts/{pin['artifact']}/zip"])
    require(len(raw) == pin["bytes"] and hashlib.sha256(raw).hexdigest() == pin["sha256"], "Downloaded archive differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        require(len(names) == len({n.casefold() for n in names}) and names.count("verified-native-transaction.json") == 1, "Ambiguous report archive")
        require(archive.getinfo("verified-native-transaction.json").file_size <= 4 * 1024 * 1024, "Oversized native report")
        report = archive.read("verified-native-transaction.json")
    result = summarize(json.loads(report))
    result.update(role="AUTHENTICATED_NATIVE_TWO_CONTROLLER_CUTS_AND_LIVE_QUARANTINE_NOT_RELEASE",
                  producer=pin, report_bytes=len(report), report_sha256=hashlib.sha256(report).hexdigest())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = authenticate(json.loads(args.pin.read_bytes()))
    encoded = json.dumps(summary, sort_keys=True).encode()
    packed = base64.b64encode(zlib.compress(encoded, 9)).decode()
    require(len(packed) <= 3500, "Bounded native summary exceeded annotation budget")
    args.output.write_bytes(encoded + b"\n")
    print("::notice title=Authenticated controller crash recovery zlib base64::" + packed)


if __name__ == "__main__":
    main()

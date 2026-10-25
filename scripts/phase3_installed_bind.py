"""Replay authenticated installed-Source21 evidence, NOT new native execution.

Artifact authentication and lossless recovery are separate prerequisites. This
validator checks receipt consistency; it cannot bless arbitrary JSON as a build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PureWindowsPath


def validate(witness: dict) -> dict:
    pin, audit = witness["anchor"], witness["native_audit"]
    digest = hashlib.sha256((json.dumps(audit, indent=2) + "\n").encode()).hexdigest()
    if (
        witness["role"] != "PHASE3_REAL_VERSIONED_INNO_SOURCE_INSTALL_NOT_DELTA_ACCEPTANCE"
        or witness["native_audit_sha256"] != digest
        or pin["source_audit_sha256"] != digest
        or pin["schema"] != 2
        or pin["role"] != "PRIVATE_SOURCE_INSTALLED_ANCHOR"
        or pin["version"] != "99.30.0"
        or pin["no_browser"] is not True
        or witness["installed_source21_startup_and_restart"] is not True
        or witness["persistent_session_secret_preserved"] is not True
        or any(
            witness[k] is not False
            for k in ("native_delta_rollback_proven", "phase3_complete", "release_authorized")
        )
        or audit["native_compilation"] != "SUCCESS"
        or audit["local_preferred_source_replay"] != "SUCCESS"
        or audit["application_present"] is not False
        or audit["compiled_from_noticed_archive"] is not True
        or audit["input_source_trees_unchanged_during_compilation"] is not True
        or len(audit["preferred_source_trees"]) != 20
        or audit["dll_count"] != 21
        or len(audit["dlls"]) != 21
    ):
        raise ValueError("Installed-source scope/audit binding differs")
    cases = witness["cases"]
    if set(cases) != {"first-installed-process", "restarted-installed-process"}:
        raise ValueError("Both installed processes required")
    roots = set()
    for name, case in cases.items():
        ready, done, http = (case[k] for k in ("ready", "completed", "http"))
        activation = done["activation"]
        reuse = name == "restarted-installed-process"
        if (
            done["pid"] != ready["pid"]
            or activation["pid"] != ready["pid"]
            or done["launch_id"] == ""
            or done["startup_path"] != "START_VIRA_CMD_TO_APP_DESKTOP_ENTRY"
            or done["factory_module"] != "app.main"
            or done["renderer_module"] != "app.services.pdf_rendering"
            or done["migration_status"] != "migrated"
            or ready["migration_status"] != "migrated"
            or done["first_run"] is reuse
            or ready["first_run"] is reuse
            or done["seed"]["users_created"] != (0 if reuse else 1)
            or ready["database"] != done["database"]
            or ready["url"].rstrip("/") != f"http://127.0.0.1:{pin['port']}"
            or ready["browser_requested"] is not False
            or ready["browser_opened"] is not False
            or ready["browser_gated_on_health"] is not True
            or activation["windows_acp"] != 65001
            or activation["dll_count"] != 21
            or activation["manifest_sha256"] != pin["manifest_sha256"]
            or activation["inventory_sha256"] != pin["inventory_sha256"]
            or activation["source_audit_sha256"] != digest
            or set(done["loaded_dlls"]) != set(audit["dlls"])
            or done["pango_version"] != "1.58.0-vira-local-source"
            or any(
                done[k] is not True
                for k in ("graceful_shutdown", "bootstrap_temp_cleaned", "desktop_lock_released")
            )
            or any(
                done[k] is not False
                for k in (
                    "qa_worker_executed",
                    "qa_factory_or_renderer_replacement",
                    "ordinary_default_enabled",
                    "release_authorized",
                )
            )
            or http["transport"] != "REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT"
            or http["prior_process_session_accepted_before_new_login"] is not reuse
            or http["live"] != {"status": "alive"}
            or http["ready"]["status"] != "ready"
            or not http["ready"]["alembic_revision"]
            or any(
                http[k] is not True
                for k in (
                    "compiled_spa_served",
                    "production_openapi_route",
                    "unauthorized_pdf_rejected",
                    "wrong_login_rejected",
                    "missing_csrf_rejected",
                    "authenticated_owner_session",
                    "route_context_from_sqlite",
                    "existing_db_session_serialization_preserved",
                )
            )
        ):
            raise ValueError("Installed process/HTTP/lifecycle binding differs")
        native = PureWindowsPath(activation["libffi"]).parent
        if native.parts[-3:] != ("native", "pdf", "bin"):
            raise ValueError("Unexpected installed native directory")
        roots.add(native)
        for dll, path in done["loaded_dlls"].items():
            if PureWindowsPath(path) != native / dll:
                raise ValueError("Foreign installed DLL origin")
        expected_documents = {
            "single-page",
            "multi-page",
            "parallel-single-page",
            "parallel-multi-page",
        }
        if (
            set(case["documents"]) != expected_documents
            or set(http["documents"]) != expected_documents
        ):
            raise ValueError("All four actual HTTP PDFs required")
        for docname, doc in case["documents"].items():
            response = http["documents"][docname]
            if doc["pages"] != (4 if "multi" in docname else 1) or any(
                doc[k] != response[k] for k in ("sha256", "bytes")
            ):
                raise ValueError("Installed PDF/HTTP bytes or pagination differ")
        fonts = case["font_documents"]
        if (
            len(fonts) != 4
            or case["peak_concurrent_documents"] not in (1, 2)
            or any(len({f[k] for f in fonts}) != 4 for k in ("font_folder", "cache_folder"))
            or any(
                f["system_fonts"] != 0 or not f["font_temp_cleaned"] or not f["cache_temp_cleaned"]
                for f in fonts
            )
        ):
            raise ValueError("Installed document font/cache isolation differs")
    first, again = (cases[n] for n in ("first-installed-process", "restarted-installed-process"))
    if (
        len(roots) != 1
        or first["ready"]["pid"] == again["ready"]["pid"]
        or first["completed"]["launch_id"] == again["completed"]["launch_id"]
        or first["ready"]["database"] != again["ready"]["database"]
        or first["http"]["fixture_ids"] != again["http"]["fixture_ids"]
        or first["completed"]["activation"]["bootstrap_temp"]
        == again["completed"]["activation"]["bootstrap_temp"]
    ):
        raise ValueError("Installed restart identity/persistence differs")
    return witness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    raw = args.witness.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.expected_sha256:
        raise ValueError("Authenticated witness digest differs")
    validate(json.loads(raw))
    print("PASS: receipt consistency only; Source21 install/restart NOT delta/rollback acceptance")


if __name__ == "__main__":
    main()

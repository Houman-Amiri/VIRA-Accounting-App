"""Validate/bind Phase 2 REAL CMD witness; metadata is not release approval."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import runpy
import zlib
from pathlib import Path


def validate(result, audit_path):
    raw = audit_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    audit = json.loads(raw)
    validator = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "backend/app/private_pdf_bootstrap.py")
    )["validate_private_source_inventory"]
    validator(result["inventory"], audit, digest)
    if (
        result["role"] != "PHASE2_REAL_START_VIRA_CMD_SOURCE_CANDIDATE_NOT_INSTALLED"
        or result["native_audit"] != audit
        or result["native_audit_sha256"] != digest
        or any(
            result[k] is not True
            for k in (
                "real_launcher_owns_migration_seed_factory_server",
                "qa_only_external_process_and_http_client",
                "inherited_user_data_sentinel_preserved",
                "blocked_update_database_unchanged",
            )
        )
        or any(
            result[k] is not False
            for k in ("ordinary_default_enabled", "installed_user_acceptance", "release_authorized")
        )
    ):
        raise ValueError("Real desktop scope/source evidence missing")
    if set(result["cases"]) != {"first-process", "restarted-process"}:
        raise ValueError("Both real desktop processes required")
    for name, c in result["cases"].items():
        r, p, h = c["ready"], c["completed"], c["http"]
        a = p["activation"]
        reuse = name == "restarted-process"
        if (
            p["startup_path"] != "START_VIRA_CMD_TO_APP_DESKTOP_ENTRY"
            or p["pid"] != r["pid"]
            or a["pid"] != r["pid"]
            or p["factory_module"] != "app.main"
            or p["renderer_module"] != "app.services.pdf_rendering"
            or a["windows_acp"] != 65001
            or a["dll_count"] != 21
            or a["source_audit_sha256"] != digest
            or a["role"] != "APP_OWNED_PRIVATE_SOURCE_ACTIVATION_NOT_INSTALLED"
            or a["manifest_sha256"] != result["payload_manifest_sha256"]
            or a["inventory_sha256"] != result["inventory_sha256"]
            or p["first_run"] is reuse
            or r["first_run"] is reuse
            or r["database"] != p["database"]
            or p["migration_status"] != "migrated"
            or r["migration_status"] != "migrated"
            or p["seed"]["users_created"] != (0 if reuse else 1)
            or p["pango_version"] != "1.58.0-vira-local-source"
            or set(p["loaded_dlls"]) != set(audit["dlls"])
            or not all(
                p[k] is True
                for k in ("graceful_shutdown", "bootstrap_temp_cleaned", "desktop_lock_released")
            )
            or any(
                p[k] is not False
                for k in (
                    "qa_worker_executed",
                    "qa_factory_or_renderer_replacement",
                    "ordinary_default_enabled",
                    "release_authorized",
                )
            )
            or not r["browser_gated_on_health"]
            or r["browser_requested"]
            or r["browser_opened"]
            or not c["persistent_secret_preserved"]
            or h["transport"] != "REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT"
            or h["prior_process_session_accepted_before_new_login"] is not reuse
            or h["live"] != {"status": "alive"}
            or h["ready"]["status"] != "ready"
            or not h["ready"]["alembic_revision"]
            or len(c["documents"]) != 4
            or len(c["font_documents"]) != 4
            or c["peak_concurrent_documents"] not in (1, 2)
        ):
            raise ValueError("Real desktop startup/process binding differs")
        if not all(
            h[k] is True
            for k in (
                "compiled_spa_served",
                "production_openapi_route",
                "unauthorized_pdf_rejected",
                "wrong_login_rejected",
                "missing_csrf_rejected",
                "authenticated_owner_session",
                "route_context_from_sqlite",
            )
        ):
            raise ValueError("Real desktop authenticated routes missing")
        for n, d in c["documents"].items():
            response = h["documents"][n]
            if d["pages"] != (4 if "multi" in n else 1) or any(
                d[k] != response[k] for k in ("sha256", "bytes")
            ):
                raise ValueError("Real desktop PDF/HTTP bytes differ")
        for kind in ("font_folder", "cache_folder"):
            if len({v[kind] for v in c["font_documents"]}) != 4:
                raise ValueError("Real desktop shares native document resources")
        if any(
            v["system_fonts"] != 0 or not v["font_temp_cleaned"] or not v["cache_temp_cleaned"]
            for v in c["font_documents"]
        ):
            raise ValueError("Real desktop document cleanup differs")
    first, again = [result["cases"][n] for n in ("first-process", "restarted-process")]
    if (
        first["ready"]["pid"] == again["ready"]["pid"]
        or first["ready"]["database"] != again["ready"]["database"]
        or first["completed"]["activation"]["bootstrap_temp"]
        == again["completed"]["activation"]["bootstrap_temp"]
        or first["http"]["fixture_ids"] != again["http"]["fixture_ids"]
    ):
        raise ValueError("Real desktop restart identity differs")
    negatives = result["negative_controls"]
    if set(negatives) != {
        "wrong-manifest",
        "wrong-source-audit",
        "duplicate-instance",
        "update-lock",
    } or any(
        v["exit_code"] == 0
        or not v["rejected"]
        or not v["ready_receipt_absent"]
        or v["pre_native_and_pre_app_rejection"] is not True
        for v in negatives.values()
    ):
        raise ValueError("Real CMD negative controls missing")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--emit-group", type=int, choices=range(8))
    args = parser.parse_args()
    path = args.reports / "verified-desktop-source.json"
    raw = path.read_bytes()
    if args.emit_group is not None:
        encoded = base64.b64encode(zlib.compress(raw, 9)).decode()
        parts = [encoded[n : n + 3000] for n in range(0, len(encoded), 3000)]
        if len(parts) > 64:
            raise ValueError("Refuse truncated real CMD witness")
        for i in range(args.emit_group * 8, min(len(parts), (args.emit_group + 1) * 8)):
            print(
                "::notice title=Phase 2 real CMD evidence::"
                + json.dumps({"part": i, "total": len(parts), "data": parts[i]})
            )
        return
    if args.audit is None:
        raise ValueError("Independent source audit required")
    validate(json.loads(raw), args.audit)
    print(
        "::notice title=Phase 2 real CMD witness digest::"
        + json.dumps({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    )


if __name__ == "__main__":
    main()

"""External-only QA client for the REAL start_vira.cmd candidate. No app imports."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path

DIGITS = "0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"


def checked(response, status):
    if response.status_code != status:
        # Do not dump login bodies, cookies, credentials or arbitrary response text.
        raise ValueError(
            f"HTTP {response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}"
        )
    return response


def exercise_http(url, state, out, password, reuse, persistent_session):
    import httpx

    manifest = state / "http-fixtures.json"
    with httpx.Client(base_url=url, timeout=120, trust_env=False) as client:
        live = checked(client.get("/api/v1/health/live"), 200).json()
        ready = checked(client.get("/api/v1/health/ready"), 200).json()
        if (
            live != {"status": "alive"}
            or ready["status"] != "ready"
            or not ready["alembic_revision"]
        ):
            raise ValueError("Production health/readiness/migration gate failed")
        spa = checked(client.get("/"), 200)
        if 'name="vira-build"' not in spa.text:
            raise ValueError("Staged compiled SPA is not served by the real factory")
        if reuse:
            client.cookies.update(persistent_session)
            owner = checked(client.get("/api/v1/auth/me"), 200).json()
            if owner["username"] != "owner":
                raise ValueError("Existing desktop session was not preserved")
            client.cookies.clear()
        schema = checked(client.get("/api/openapi.json"), 200).json()
        if "/api/v1/orders/{order_id}/proforma.pdf" not in schema["paths"]:
            raise ValueError("Actual production PDF route missing")
        checked(client.get("/api/v1/orders/not-an-order/proforma.pdf"), 401)
        checked(
            client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "intentionally-wrong-private-password"},
            ),
            401,
        )
        login = checked(
            client.post("/api/v1/auth/login", json={"username": "owner", "password": password}), 200
        )
        persistent_session.clear()
        persistent_session.update(dict(client.cookies))
        if not any("httponly" in v.lower() for v in login.headers.get_list("set-cookie")):
            raise ValueError("Real session cookie was not issued")
        checked(client.post("/api/v1/orders", json={}), 403)
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        client.headers["Origin"] = url
        if reuse:
            fixtures = json.loads(manifest.read_text(encoding="utf-8"))
        else:
            fixtures = {}
            for name, count in [("single-page", 1), ("multi-page", 100)]:
                payload = {
                    "order_date": "2026-10-19",
                    "customer_name": "آزمایش خصوصی " + DIGITS,
                    "customer_phone": DIGITS,
                    "customer_address": "فقط داده ساختگی تهران",
                    "items": [
                        {
                            "product_name": "مدل " + DIGITS,
                            "quantity": "1",
                            "unit_price": "1234567890.1",
                            "unit_cost": "10",
                        }
                        for _ in range(count)
                    ],
                }
                order = checked(client.post("/api/v1/orders", json=payload), 201).json()
                fixtures[name] = order["id"]
            manifest.write_text(json.dumps(fixtures), encoding="utf-8")
        if set(fixtures) != {"single-page", "multi-page"}:
            raise ValueError("Unexpected persistent HTTP fixture IDs")
        for name, count in [("single-page", 1), ("multi-page", 100)]:
            order = checked(client.get("/api/v1/orders/" + fixtures[name]), 200).json()
            if len(order["items"]) != count or Decimal(order["total"]) != count * Decimal(
                "1234567890.1"
            ):
                raise ValueError("Persisted real-route order changed across restart")
        documents = {}
        request_barrier = threading.Barrier(2)

        def download(name, filename):
            if filename.startswith("parallel-"):
                request_barrier.wait(timeout=15)
            response = checked(client.get(f"/api/v1/orders/{fixtures[name]}/proforma.pdf"), 200)
            if response.headers.get(
                "content-type"
            ) != "application/pdf" or not response.content.startswith(b"%PDF-"):
                raise ValueError("HTTP HTML fallback is NOT native PDF proof")
            if not response.headers.get("content-disposition", "").endswith('.pdf"'):
                raise ValueError("HTTP PDF disposition is incorrect")
            (out / f"{filename}.pdf").write_bytes(response.content)
            return {
                "status": 200,
                "content_type": "application/pdf",
                "bytes": len(response.content),
                "sha256": hashlib.sha256(response.content).hexdigest(),
            }

        for name in fixtures:
            documents[name] = download(name, name)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending = {name: pool.submit(download, name, "parallel-" + name) for name in fixtures}
            for name, task in pending.items():
                documents["parallel-" + name] = task.result(timeout=150)
    return {
        "transport": "REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT",
        "lifespan_started": True,
        "live": live,
        "ready": ready,
        "compiled_spa_served": True,
        "production_openapi_route": True,
        "unauthorized_pdf_rejected": True,
        "wrong_login_rejected": True,
        "missing_csrf_rejected": True,
        "authenticated_owner_session": True,
        "prior_process_session_accepted_before_new_login": reuse,
        "route_context_from_sqlite": True,
        "fixture_ids": fixtures,
        "parallel_http_requests": 2,
        "existing_db_session_serialization_preserved": True,
        "documents": documents,
    }


def read(path):
    return json.loads(path.read_bytes().decode("utf-8-sig"))


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())


def launch(root, request, log, environment):
    # Explicit cmd.exe, fixed script, quoted file path; no shell-supplied code.
    command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{root / "start_vira.cmd"}" --private-source-candidate "{request}""'
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)


def wait_file(path, process, timeout=150):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return read(path)
        if process.poll() is not None:
            raise RuntimeError("Real desktop process exited before readiness")
        time.sleep(0.1)
    raise RuntimeError("Real desktop startup timed out")


def verify_events(path, root):
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    active = set()
    completed = []
    peak = 0
    for event in events:
        if event["event"] == "started":
            if event["id"] in active:
                raise ValueError("Duplicate desktop document start")
            active.add(event["id"])
            peak = max(peak, len(active))
        elif event["event"] == "completed":
            active.remove(event["id"])
            completed.append(event)
        else:
            raise ValueError("Failed desktop document")
    if active or len(completed) != 4 or peak not in (1, 2):
        raise ValueError("Desktop document lifecycle incomplete")
    expected = sorted(
        hashlib.sha256((root / "app/assets/fonts" / f"Vazirmatn-{w}.ttf").read_bytes()).hexdigest()
        for w in ("Regular", "Bold")
    )
    if any(
        v["system_fonts"] != 0
        or v["font_sha256"] != expected
        or not v["font_temp_cleaned"]
        or not v["cache_temp_cleaned"]
        for v in completed
    ):
        raise ValueError("Desktop font/cache invariants failed")
    if (
        len({v["font_folder"] for v in completed}) != 4
        or len({v["cache_folder"] for v in completed}) != 4
    ):
        raise ValueError("Desktop document resources shared")
    return completed, peak


def main():
    from pdf_native_smoke import inspect_pdf

    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("app-root", "state-root", "reports", "audit"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Private Windows real-launcher QA only")
    root, state, reports = args.app_root, args.state_root, args.reports
    reports.mkdir(parents=True, exist_ok=True)
    requests = state.parent / "desktop requests"
    requests.mkdir(parents=True)
    audit_digest = hashlib.sha256(args.audit.read_bytes()).hexdigest()
    password = secrets.token_urlsafe(40)
    env = dict(os.environ, VIRA_ADMIN_PASSWORD=password)
    # Poison inherited settings to prove the candidate does not use normal user data.
    outside = state.parent / "outside sentinel"
    outside.mkdir()
    sentinel = outside / "must-preserve.sqlite3"
    sentinel.write_bytes(b"NOT A DATABASE; NEVER OPEN")
    env.update(DATA_DIR=str(outside), SQLITE_DATABASE_PATH=str(sentinel), ENVIRONMENT="production")
    cases = {}
    negatives = {}

    def request(overrides=None):
        value = {
            "role": "PRIVATE_SOURCE_DESKTOP_REQUEST",
            "manifest_sha256": args.manifest_sha256,
            "inventory_sha256": args.inventory_sha256,
            "source_audit_sha256": audit_digest,
            "state_root": str(state),
            "launch_id": uuid.uuid4().hex,
            "port": 0,
            "no_browser": True,
        }
        value.update(overrides or {})
        path = requests / (value["launch_id"] + ".json")
        dump(path, value)
        return path, value

    def rejected(name, overrides=None):
        path, value = request(overrides)
        with (reports / (name + ".log")).open("wb") as log:
            p = launch(root, path, log, env)
            try:
                code = p.wait(timeout=150)
            except BaseException:
                p.kill()
                p.wait()
                raise
        if code == 0 or (state / "launches" / value["launch_id"] / "ready.json").exists():
            raise ValueError("Invalid real launcher accepted " + name)
        expected = {
            "wrong-manifest": "MANIFEST_DIGEST",
            "wrong-source-audit": "BOOTSTRAP_DIGEST",
            "duplicate-instance": "DESKTOP_INSTANCE_LOCK",
            "update-lock": "UPDATE_LOCK",
        }[name]
        if "startup rejected: " + expected not in (reports / (name + ".log")).read_text(
            encoding="utf-8-sig"
        ):
            raise ValueError("Invalid launcher rejection reason: " + name)
        if "; native_imported=0; app_imported=0" not in (reports / (name + ".log")).read_text(
            encoding="utf-8-sig"
        ):
            raise ValueError("Rejected startup imported app/native modules: " + name)
        negatives[name] = {
            "pre_native_and_pre_app_rejection": True,
            "failure_kind": expected,
            "rejected": True,
            "exit_code": code,
            "ready_receipt_absent": True,
        }

    rejected("wrong-manifest", {"manifest_sha256": "0" * 64})
    if args.preflight_only:
        if state.exists():
            raise ValueError("Rejected preflight touched business state")
        dump(
            reports / "real-cmd-path-preflight-only.json",
            {
                "role": "REAL_CMD_WRONG_MANIFEST_ONLY_NOT_NATIVE_OR_SOURCE_ACTIVATION",
                "negative_controls": negatives,
                "native_activation_proven": False,
            },
        )
        return
    rejected("wrong-source-audit", {"source_audit_sha256": "0" * 64})
    if state.exists():
        raise ValueError("Rejected preflight touched business state")
    secret_hash = None
    persistent_session = {}
    for name, reuse in [("first-process", False), ("restarted-process", True)]:
        out = reports / name
        out.mkdir()
        path, value = request()
        folder = state / "launches" / value["launch_id"]
        with (out / "launcher.log").open("wb") as log:
            process = launch(root, path, log, env)
            try:
                ready = wait_file(folder / "ready.json", process)
                if (
                    ready["first_run"] is reuse
                    or ready["browser_requested"]
                    or not ready["browser_gated_on_health"]
                ):
                    raise ValueError("Desktop first-run/browser gate differs")
                if not reuse:
                    rejected("duplicate-instance")
                http = exercise_http(ready["url"], state, out, password, reuse, persistent_session)
                dump(folder / "stop.json", {"pid": ready["pid"], "launch_id": value["launch_id"]})
                code = process.wait(timeout=45)
                if code != 0:
                    raise ValueError("Desktop launcher exited nonzero")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                    raise RuntimeError("Desktop QA had to force-kill process; not graceful success")
        completed = read(folder / "completed.json")
        if (
            completed["pid"] != ready["pid"]
            or not completed["graceful_shutdown"]
            or not completed["bootstrap_temp_cleaned"]
            or not completed["desktop_lock_released"]
            or completed["qa_worker_executed"]
            or completed["qa_factory_or_renderer_replacement"]
        ):
            raise ValueError("Actual desktop process completion invalid")
        events, peak = verify_events(folder / "pdf-lifecycles.jsonl", root)
        documents = {}
        for filename, response in http["documents"].items():
            data = (out / (filename + ".pdf")).read_bytes()
            if hashlib.sha256(data).hexdigest() != response["sha256"]:
                raise ValueError("Desktop HTTP PDF binding differs")
            doc = inspect_pdf(
                data,
                expected_by_weight={400: DIGITS, 700: "۰۱۲۳۴۵۶۷۸۹"},
                min_pages=2 if "multi" in filename else 1,
            )
            if doc["pages"] != (4 if "multi" in filename else 1):
                raise ValueError("Desktop pagination differs")
            documents[filename] = doc
        current_secret = hashlib.sha256((state / "session.secret").read_bytes()).hexdigest()
        if secret_hash is not None and current_secret != secret_hash:
            raise ValueError("Desktop session secret changed across restart")
        secret_hash = current_secret
        cases[name] = {
            "ready": ready,
            "completed": completed,
            "http": http,
            "font_documents": events,
            "peak_concurrent_documents": peak,
            "documents": documents,
            "persistent_secret_preserved": True,
        }
        dump(out / "verified-desktop-process.json", cases[name])
    if cases["first-process"]["ready"]["pid"] == cases["restarted-process"]["ready"]["pid"]:
        raise ValueError("Desktop restart reused process")
    if (
        cases["first-process"]["http"]["fixture_ids"]
        != cases["restarted-process"]["http"]["fixture_ids"]
    ):
        raise ValueError("Desktop restart IDs changed")
    db = Path(cases["first-process"]["ready"]["database"])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    lock = state / "data/updates/.update.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"PRIVATE BLOCKING UPDATE")
    try:
        rejected("update-lock")
    finally:
        lock.unlink()
    if (
        hashlib.sha256(db.read_bytes()).hexdigest() != before
        or sentinel.read_bytes() != b"NOT A DATABASE; NEVER OPEN"
    ):
        raise ValueError("Blocked startup modified DB or inherited user sentinel")
    manifest = read(root / "install_manifest.json")
    for file in manifest["files"]:
        if hashlib.sha256((root / file["path"]).read_bytes()).hexdigest() != file["sha256"]:
            raise ValueError("Real desktop modified payload baseline")
    result = {
        "schema": 1,
        "role": "PHASE2_REAL_START_VIRA_CMD_SOURCE_CANDIDATE_NOT_INSTALLED",
        "cases": cases,
        "negative_controls": negatives,
        "native_audit": read(args.audit),
        "native_audit_sha256": audit_digest,
        "inventory": read(root / "native/pdf/runtime-inventory.json"),
        "payload_manifest_sha256": args.manifest_sha256,
        "inventory_sha256": args.inventory_sha256,
        "real_launcher_owns_migration_seed_factory_server": True,
        "qa_only_external_process_and_http_client": True,
        "ordinary_default_enabled": False,
        "installed_user_acceptance": False,
        "release_authorized": False,
        "inherited_user_data_sentinel_preserved": True,
        "blocked_update_database_unchanged": True,
    }
    dump(reports / "verified-desktop-source.json", result)


if __name__ == "__main__":
    main()

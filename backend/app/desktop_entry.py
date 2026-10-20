"""Real start_vira.cmd candidate entry. Explicit private SOURCE mode only.

Stdlib before audited native activation. No QA imports, injected factories or
HTTP shutdown endpoint. Default launcher is unchanged. Not distribution approval.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import runpy
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate request key")
        result[key] = value
    return result


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes().decode("utf-8-sig"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Startup object required")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    # Exact LF bytes on Windows too; atomic visibility for readiness receipts.
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes((json.dumps(value, indent=2) + "\n").encode("utf-8"))
    temp.replace(path)


def request(root: Path, file: Path) -> dict[str, Any]:
    value = read(file)
    keys = {
        "role",
        "manifest_sha256",
        "inventory_sha256",
        "source_audit_sha256",
        "state_root",
        "launch_id",
        "port",
        "no_browser",
    }
    if (
        set(value) != keys
        or value["role"] != "PRIVATE_SOURCE_DESKTOP_REQUEST"
        or not isinstance(value["launch_id"], str)
        or re.fullmatch(r"[0-9a-f]{32}", value["launch_id"]) is None
        or type(value["port"]) is not int
        or not 0 <= value["port"] <= 65535
        or type(value["no_browser"]) is not bool
    ):
        raise ValueError("Invalid explicit desktop candidate request")
    for key in ("manifest_sha256", "inventory_sha256", "source_audit_sha256"):
        if not isinstance(value[key], str) or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None:
            raise ValueError("Independent startup SHA256 required")
    state = Path(value["state_root"])
    profile = Path(os.environ["LOCALAPPDATA"])
    if (
        not state.is_absolute()
        or ".." in state.parts
        or not state.is_relative_to(profile)
        or state == profile
        or state.is_relative_to(root)
        or root.is_relative_to(state)
    ):
        raise ValueError("Private desktop state must be disjoint below profile")
    return value


@contextmanager
def environment(values: dict[str, str]):  # type: ignore[no-untyped-def]
    old = {k: os.environ.get(k) for k in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def state_guard(root: Path, state: Path, check):  # type: ignore[no-untyped-def]
    """Private marker + exclusive lifetime lock. Never delete an unowned stale lock."""
    check(state)
    pending = [state] if state.exists() else []
    while pending:
        for child in pending.pop().iterdir():
            check(child)
            if child.is_dir():
                pending.append(child)
    marker = state / "private-desktop-state.json"
    expected = {"schema": 1, "role": "PRIVATE_SOURCE_DESKTOP_STATE", "payload_root": str(root)}
    if (
        state.exists()
        and any(state.iterdir())
        and (not marker.is_file() or read(marker) != expected)
    ):
        raise ValueError("Existing state is not this private desktop candidate")
    state.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        with marker.open("xb") as stream:
            stream.write((json.dumps(expected) + "\n").encode())
    lock = state / ".desktop.lock"
    token = secrets.token_hex(24)
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(token)
    try:
        if (state / "data/updates/.update.lock").exists():
            raise ValueError("Update in progress; candidate startup blocked")
        yield
    finally:
        check(lock)
        if lock.read_text(encoding="utf-8") != token:
            raise RuntimeError("Desktop lifetime lock ownership changed")
        lock.unlink()


class LifecycleFile(logging.Handler):
    """Application-owned fixed diagnostics, not a caller-supplied renderer hook."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.stream = path.open("xb")

    def emit(self, record: logging.LogRecord) -> None:
        event = getattr(record, "pdf_document", None)
        if isinstance(event, dict):
            self.stream.write((json.dumps(event) + "\n").encode("utf-8"))
            self.stream.flush()

    def close(self) -> None:
        self.stream.close()
        super().close()


def native_state(root: Path) -> dict[str, Any]:
    inventory = read(root / "native/pdf/runtime-inventory.json")
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    loaded = {}
    for name in inventory["dlls"]:
        buffer = ctypes.create_unicode_buffer(32768)
        handle = kernel.GetModuleHandleW(name)
        if not handle or not kernel.GetModuleFileNameW(handle, buffer, len(buffer)):
            raise RuntimeError("Audited desktop native module absent")
        if Path(buffer.value).resolve() != root / "native/pdf/bin" / name:
            raise RuntimeError("Foreign desktop native module")
        loaded[name] = buffer.value
    pango = ctypes.CDLL(str(root / "native/pdf/bin/pango-1.0-0.dll"))
    pango.pango_version_string.restype = ctypes.c_char_p
    version = pango.pango_version_string().decode("ascii")
    if version != "1.58.0-vira-local-source":
        raise RuntimeError("Desktop source function mismatch")
    return {"loaded_dlls": loaded, "pango_version": version}


def serve(root: Path, state: Path, launch: Path, options: dict[str, Any]) -> dict[str, Any]:
    """Own migration/seed/factory/server/browser readiness, no QA worker execution."""
    from app.config import load_settings
    from app.db import Database
    from app.seed import seed_all
    from app.services.pdf_rendering import PdfRenderer, PrivatePdfPolicy

    data = state / "data"
    database = data / "data/vira.sqlite3"
    first = not database.exists()
    password = os.environ.get("VIRA_ADMIN_PASSWORD", "")
    if len(password) < 32:
        raise ValueError("Private owner credential required")
    secret = state / "session.secret"
    if not secret.exists():
        with secret.open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(48))
    session_secret = secret.read_text(encoding="utf-8")
    if len(session_secret) < 32:
        raise ValueError("Invalid persistent desktop session secret")
    values = {
        "DATA_DIR": str(data),
        "SQLITE_DATABASE_PATH": str(database),
        "RECEIPT_DIR": str(data / "receipts"),
        "SESSION_SECRET": session_secret,
        "ENVIRONMENT": "development",
        "STRICT_SECRETS": "false",
        "SCHEDULER_ENABLED": "false",
        "STORAGE_PROVIDER": "local",
        "VIRA_APP_DIR": str(root),
    }
    with environment(values):
        migration = runpy.run_path(str(root / "scripts/migrate_vira.py"))["run_migration"](
            database, None
        )
        settings = load_settings(
            _env_file=None, **{k.lower(): v for k, v in values.items() if k != "VIRA_APP_DIR"}
        )
        # Production seed is idempotent: also repairs a first launch interrupted
        # after migration, without replacing an existing owner's password/data.
        db = Database(settings)
        try:
            with db.write_session() as session:
                seeded = seed_all(session, admin_password=password)
        finally:
            db.dispose()
        import uvicorn

        from app.main import create_app

        app = create_app(settings, private_pdf_policy=PrivatePdfPolicy(state / "pdf-cache"))
        if type(app.state.pdf_renderer) is not PdfRenderer:
            raise RuntimeError("Desktop factory did not select app-owned renderer")
        logger = logging.getLogger("app.services.pdf_rendering")
        level, disabled = logger.level, logger.disabled
        events = LifecycleFile(launch / "pdf-lifecycles.jsonl")
        logger.disabled = False
        logger.setLevel(logging.INFO)
        logger.addHandler(events)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server = None
        watcher = None
        finished = threading.Event()
        monitor_errors: list[str] = []
        url = ""
        try:
            sock.bind(("127.0.0.1", options["port"]))
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=0,
                    lifespan="on",
                    loop="asyncio",
                    access_log=False,
                    log_level="warning",
                )
            )

            def monitor() -> None:
                assert server is not None
                try:
                    deadline = time.monotonic() + 90
                    while not server.started:
                        if finished.wait(0.05) or time.monotonic() >= deadline:
                            raise RuntimeError("Desktop server startup deadline")
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    for endpoint in ("live", "ready"):
                        with opener.open(url + "/api/v1/health/" + endpoint, timeout=5) as response:  # noqa: S310
                            health = json.loads(response.read())
                            expected = "alive" if endpoint == "live" else "ready"
                            if response.status != 200 or health.get("status") != expected:
                                raise RuntimeError("Desktop health gate failed")
                            if endpoint == "ready" and not health.get("alembic_revision"):
                                raise RuntimeError("Desktop migration readiness gate failed")
                    browser = False if options["no_browser"] else webbrowser.open(url)
                    write(
                        launch / "ready.json",
                        {
                            "role": "PRIVATE_REAL_DESKTOP_READY_NOT_INSTALLED",
                            "pid": os.getpid(),
                            "url": url,
                            "database": str(database),
                            "migration_status": migration["status"],
                            "first_run": first,
                            "seed": seeded,
                            "browser_requested": not options["no_browser"],
                            "browser_opened": browser,
                            "browser_gated_on_health": True,
                        },
                    )
                    while not finished.wait(0.1):
                        stop = launch / "stop.json"
                        if stop.exists():
                            # Private owner control only, no network shutdown route.
                            if stop.is_symlink() or read(stop) != {
                                "pid": os.getpid(),
                                "launch_id": options["launch_id"],
                            }:
                                raise ValueError("Foreign desktop stop request")
                            server.should_exit = True
                            return
                except BaseException as exc:
                    monitor_errors.append(type(exc).__name__)
                    server.should_exit = True

            watcher = threading.Thread(target=monitor, name="VIRA desktop readiness", daemon=True)
            watcher.start()
            server.run(sockets=[sock])
        finally:
            finished.set()
            if watcher is not None:
                watcher.join(timeout=8)
            sock.close()
            logger.removeHandler(events)
            logger.setLevel(level)
            logger.disabled = disabled
            events.close()
        if (
            monitor_errors
            or server is None
            or not server.started
            or not (launch / "ready.json").is_file()
        ):
            raise RuntimeError("Desktop startup/monitor failed")
        return {
            "migration_status": migration["status"],
            "first_run": first,
            "seed": seeded,
            "database": str(database),
            "url": url,
            "graceful_shutdown": True,
            "factory_module": create_app.__module__,
            "renderer_module": PdfRenderer.__module__,
            **native_state(root),
        }


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--private-source-candidate":
        raise ValueError("Explicit private desktop source request required")
    if os.environ.get("VIRA_LAUNCHER_ENTRY") != "START_VIRA_CMD_PRIVATE_SOURCE":
        raise ValueError("Use the real start_vira.cmd entry")
    root = Path(__file__).resolve().parents[1]
    options = request(root, Path(sys.argv[2]))
    raw = (root / "install_manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != options["manifest_sha256"]:
        raise ValueError("Independent desktop manifest mismatch")
    baseline = json.loads(raw, object_pairs_hook=unique)
    module = root / "app/private_pdf_bootstrap.py"
    entries = [e for e in baseline["files"] if e["path"] == "app/private_pdf_bootstrap.py"]
    if len(entries) != 1 or hashlib.sha256(module.read_bytes()).hexdigest() != entries[0]["sha256"]:
        raise ValueError("Desktop bootstrap code differs before execution")
    boot = runpy.run_path(str(module))
    state = Path(options["state_root"])
    boot["_no_links"](Path(sys.argv[2]))
    boot["_no_links"](state)
    bootstrap_state = state.parent / ("bootstrap-" + options["launch_id"])
    plan = boot["PrivateBootstrapPlan"](
        root,
        bootstrap_state,
        options["manifest_sha256"],
        options["inventory_sha256"],
        source_audit_sha256=options["source_audit_sha256"],
    )
    # Reject changed payload/source before touching business state, then acquire
    # the lifetime/update guards BEFORE any native DLL import. Activation still
    # repeats the full audit at the loading boundary; this is not a cached bypass.
    boot["prepare_private_plan"](plan)
    with (
        state_guard(root, state, boot["_no_links"]),
        boot["activate_private_source"](plan) as active,
    ):
        launch = state / "launches" / options["launch_id"]
        launch.mkdir(parents=True, exist_ok=False)
        result = serve(root, state, launch, options)
        result.update(
            role="PRIVATE_REAL_START_VIRA_SOURCE_NOT_INSTALLED_ACCEPTANCE",
            pid=os.getpid(),
            launch_id=options["launch_id"],
            activation=asdict(active),
            startup_path="START_VIRA_CMD_TO_APP_DESKTOP_ENTRY",
            qa_worker_executed=False,
            qa_factory_or_renderer_replacement=False,
            ordinary_default_enabled=False,
            release_authorized=False,
        )
    result.update(
        bootstrap_temp_cleaned=not Path(active.bootstrap_temp).exists(),
        desktop_lock_released=not (state / ".desktop.lock").exists(),
    )
    write(launch / "completed.json", result)
    return 0


def failure_kind(exc: Exception) -> str:
    """Bounded diagnostics: never print credentials, SQL params or request data."""
    if isinstance(exc, FileExistsError) and str(exc.filename).endswith(".desktop.lock"):
        return "DESKTOP_INSTANCE_LOCK"
    known = {
        "Update in progress; candidate startup blocked": "UPDATE_LOCK",
        "Independent desktop manifest mismatch": "MANIFEST_DIGEST",
        "Independent digest mismatch": "BOOTSTRAP_DIGEST",
    }
    return known.get(str(exc), type(exc).__name__)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        native = any(n in sys.modules for n in ("ctypes", "_ctypes", "cffi", "_cffi_backend"))
        app = any(n in sys.modules for n in ("app.main", "uvicorn", "weasyprint"))
        print(
            "VIRA private desktop startup rejected: "
            + failure_kind(exc)
            + f"; native_imported={int(native)}; app_imported={int(app)}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

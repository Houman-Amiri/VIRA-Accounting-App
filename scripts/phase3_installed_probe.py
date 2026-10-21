"""External HTTP/process client: real versioned Inno install, NOT delta acceptance.

No app imports, patched callables, in-process ASGI transport or native substitutes.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

from desktop_launcher_probe import DIGITS, dump, exercise_http, read, verify_events, wait_file
from pdf_native_smoke import inspect_pdf


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("app-root", "profile", "reports", "audit"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Disposable Windows CI installed-source proof only")
    root, profile, reports = args.app_root, args.profile, args.reports
    runner = Path(os.environ["RUNNER_TEMP"])
    for path in (root, profile):
        if (
            not path.is_absolute()
            or path == runner
            or not path.is_relative_to(runner)
            or ".." in path.parts
        ):
            raise ValueError("Runner-owned selected install/profile required")
    home = profile / "VIRA/private-native-installed"
    state = home / "state"
    pin = read(home / "anchor.json")
    if (
        pin["schema"] != 2
        or pin["version"] != "99.30.0"
        or pin["source_audit_sha256"] != sha(args.audit)
    ):
        raise ValueError("Exact versioned fresh Source21 anchor required")
    if sha(root / "install_manifest.json") != pin["manifest_sha256"]:
        raise ValueError("Installed manifest differs from independent Inno input")
    reports.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(40)
    environment = dict(os.environ, LOCALAPPDATA=str(profile), VIRA_ADMIN_PASSWORD=password)
    # Version discovery must use the installed, independently anchored stamp.
    for key in ("VIRA_VERSION", "VIRA_APP_DIR", "VIRA_GIT_COMMIT"):
        environment.pop(key, None)
    sessions = {}
    cases = {}
    secret_hash = None
    for name, reuse in (("first-installed-process", False), ("restarted-installed-process", True)):
        out = reports / name
        out.mkdir()
        with (out / "launcher.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    str(root / "python/python.exe"),
                    "-I",
                    "-S",
                    "-B",
                    "-X",
                    "utf8",
                    str(root / "app/private_installed_source.py"),
                ],
                cwd=home,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            folder = None
            try:
                active = wait_file(home / "active-launch.json", process)
                folder = state / "launches" / active["launch_id"]
                ready = wait_file(folder / "ready.json", process)
                if (
                    ready["first_run"] is reuse
                    or ready["browser_requested"]
                    or not ready["browser_gated_on_health"]
                ):
                    raise ValueError("Installed first-run/browser gate differs")
                if ready["url"].rstrip("/") != f"http://127.0.0.1:{pin['port']}":
                    raise ValueError("Installed client redirected from pinned port")
                http = exercise_http(ready["url"], state, out, password, reuse, sessions)
                import httpx

                with httpx.Client(
                    base_url=ready["url"], cookies=sessions, trust_env=False, timeout=30
                ) as client:
                    if client.get("/api/v1/system/status").status_code != 403:
                        raise ValueError("Installed privileged status lost its sudo gate")
                    client.headers["X-CSRF-Token"] = sessions["vira_csrf"]
                    client.headers["Origin"] = ready["url"]
                    sudo = client.post("/api/v1/auth/sudo", json={"password": password})
                    if sudo.status_code != 200:
                        raise ValueError("Installed owner sudo elevation failed")
                    client.headers["X-Sudo-Token"] = sudo.json()["sudo_token"]
                    version = client.get("/api/v1/system/status")
                    if version.status_code != 200 or version.json()["version"] != pin["version"]:
                        raise ValueError(
                            "Running installed version differs from independent anchor"
                        )
                dump(folder / "stop.json", dict(pid=ready["pid"], launch_id=active["launch_id"]))
                if process.wait(timeout=60) != 0:
                    raise ValueError("Installed bridge/real CMD exited nonzero")
            finally:
                if folder is not None:
                    for filename in ("ready.json", "completed.json", "pdf-lifecycles.jsonl"):
                        file = folder / filename
                        if file.is_file():
                            (out / filename).write_bytes(file.read_bytes())
                if process.poll() is None:
                    if folder is not None and (folder / "ready.json").is_file():
                        r = read(folder / "ready.json")
                        dump(
                            folder / "stop.json", dict(pid=r["pid"], launch_id=active["launch_id"])
                        )
                        with suppress(subprocess.TimeoutExpired):
                            process.wait(timeout=30)
                    if process.poll() is None:
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            check=True,
                            timeout=20,
                        )
                        process.wait(timeout=20)
                        raise RuntimeError("Installed proof needed forced cleanup; not success")
        completed = read(folder / "completed.json")
        activation = completed["activation"]
        if (
            completed["pid"] != ready["pid"]
            or not completed["graceful_shutdown"]
            or not completed["bootstrap_temp_cleaned"]
            or not completed["desktop_lock_released"]
            or completed["qa_worker_executed"]
            or completed["qa_factory_or_renderer_replacement"]
            or activation["source_audit_sha256"] != pin["source_audit_sha256"]
            or activation["manifest_sha256"] != pin["manifest_sha256"]
            or activation["dll_count"] != 21
            or activation["windows_acp"] != 65001
            or len(completed["loaded_dlls"]) != 21
        ):
            raise ValueError("Installed source lifecycle/native activation differs")
        for path in completed["loaded_dlls"].values():
            if Path(path).parent != root / "native/pdf/bin":
                raise ValueError("Installed native origin differs")
        events, peak = verify_events(folder / "pdf-lifecycles.jsonl", root)
        documents = {}
        for filename, response in http["documents"].items():
            data = (out / (filename + ".pdf")).read_bytes()
            if hashlib.sha256(data).hexdigest() != response["sha256"]:
                raise ValueError("Installed HTTP PDF binding differs")
            doc = inspect_pdf(
                data,
                expected_by_weight={400: DIGITS, 700: "۰۱۲۳۴۵۶۷۸۹"},
                min_pages=2 if "multi" in filename else 1,
            )
            if doc["pages"] != (4 if "multi" in filename else 1):
                raise ValueError("Installed PDF pagination differs")
            documents[filename] = doc
        current = sha(state / "session.secret")
        if secret_hash is not None and current != secret_hash:
            raise ValueError("Installed persistent secret changed")
        secret_hash = current
        cases[name] = dict(
            ready=ready,
            completed=completed,
            http=http,
            documents=documents,
            font_documents=events,
            peak_concurrent_documents=peak,
        )
    if len({v["ready"]["pid"] for v in cases.values()}) != 2:
        raise ValueError("Installed restart did not use a fresh app process")
    if len({tuple(sorted(v["http"]["fixture_ids"].items())) for v in cases.values()}) != 1:
        raise ValueError("Installed persisted IDs changed")
    for file in read(root / "install_manifest.json")["files"]:
        if sha(root / file["path"]) != file["sha256"]:
            raise ValueError("Installed app modified baseline")
    dump(
        reports / "verified-installed-source.json",
        dict(
            role="PHASE3_REAL_VERSIONED_INNO_SOURCE_INSTALL_NOT_DELTA_ACCEPTANCE",
            native_audit_sha256=sha(args.audit),
            native_audit=read(args.audit),
            anchor=pin,
            cases=cases,
            installed_source21_startup_and_restart=True,
            persistent_session_secret_preserved=True,
            native_delta_rollback_proven=False,
            phase3_complete=False,
            release_authorized=False,
        ),
    )
    print(
        "PASS: versioned installed Source21 HTTP/PDF/restart only; NOT native delta/rollback acceptance"
    )


if __name__ == "__main__":
    main()

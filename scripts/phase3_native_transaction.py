"""External real-TCP installed Source21 delta/rollback client (private Windows CI).

No app imports, ASGI transports, QA factories/renderers/migrations or mocked
process boundaries. Native targets must already have separate cold-build audits.
Never upload the generated packages, databases, cookies, credentials or keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from contextlib import closing, suppress
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from desktop_launcher_probe import checked, dump, exercise_http, read, verify_events, wait_file
from pdf_native_smoke import inspect_pdf

REPO = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(path: Path) -> str:
    """Independent external read-only full SQL identity, not a projected balance."""
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        if (
            db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
            or db.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise ValueError("Live business DB integrity differs")
        digest = hashlib.sha256()
        for statement in db.iterdump():
            digest.update(statement.encode())
            digest.update(b"\n")
        for pragma in ("user_version", "application_id"):
            digest.update(f"{pragma}={db.execute(f'PRAGMA {pragma}').fetchone()[0]};".encode())
        return digest.hexdigest()


def run_script(name: str, *args: object) -> None:
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / name), *(str(a) for a in args)],
        check=True,
        timeout=240,
    )


def target_payload(
    base: Path, target: Path, candidate: Path, audit: Path, version: str, helper: Path, pin: dict
) -> Path:
    if target.exists():
        raise FileExistsError("Fresh disposable target payload required")
    shutil.copytree(base, target)
    # ONLY our newly created copy, never the live installation or user state.
    shutil.rmtree(target / "native/pdf")
    shutil.copytree(candidate, target / "native/pdf")
    shutil.copyfile(audit, target / "native/pdf/source-audit.json")
    shutil.copyfile(helper, target / "vira-updater.exe")
    stamp = read(target / "version.json")
    stamp["version"] = version
    dump(target / "version.json", stamp)
    run_script("build_manifest.py", target)
    new_pin = dict(
        pin,
        version=version,
        manifest_sha256=sha(target / "install_manifest.json"),
        inventory_sha256=sha(target / "native/pdf/runtime-inventory.json"),
        source_audit_sha256=sha(audit),
    )
    anchor = target.parent / (target.name + "-anchor.json")
    dump(anchor, new_pin)
    return anchor


def packet(base: Path, target: Path, anchor: Path, destination: Path) -> Path:
    base_version, version = (read(p / "version.json")["version"] for p in (base, target))
    run_script(
        "gen_delta.py",
        "--base-manifest",
        base / "install_manifest.json",
        "--base-dir",
        base,
        "--target-dir",
        target,
        "--base-version",
        base_version,
        "--target-version",
        version,
        "--out",
        destination,
        "--private-source-anchor",
        anchor,
    )
    output = destination / f"VIRA-v{version}-delta-from-v{base_version}.zip"
    check_packet(base, target, output)
    return output


def check_packet(base: Path, target: Path, archive: Path) -> dict:
    """No unchanged payload file, complete changed set, actual Pango delta."""
    old, new = (
        {f["path"]: f for f in read(p / "install_manifest.json")["files"]} for p in (base, target)
    )
    changed = {n for n in old.keys() | new.keys() if old.get(n) != new.get(n)}
    with zipfile.ZipFile(archive) as z:
        doc = json.loads(z.read("update.json"))
        if {o["path"] for o in doc["operations"]} != changed or len(doc["operations"]) != len(
            changed
        ):
            raise ValueError("Delta operation set does not exactly match changed payload files")
        if "native/pdf/bin/pango-1.0-0.dll" not in changed or "vira-updater.exe" not in changed:
            raise ValueError("Genuine native AND installed-helper replacement must be exercised")
        if any(n.endswith(".exe") and "Setup" in n for n in z.namelist()):
            raise ValueError("Full setup must never enter routine update")
        for n in z.namelist():
            if n.startswith("files/") and n[6:] not in changed:
                raise ValueError("Unchanged payload file leaked into delta")
        return dict(
            archive_sha256=sha(archive),
            bytes=archive.stat().st_size,
            changed=sorted(changed),
            native_operations=[
                o for o in doc["operations"] if o["path"].startswith("native/pdf/bin/")
            ],
            unchanged_payload_files_absent=True,
            full_installer_in_package=False,
        )


class Feed:
    """Real signed loopback mirror. Full-setup sentinel requests are fatal."""

    def __init__(self, directory: Path):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        self.key = Ed25519PrivateKey.generate()
        self.public = (
            self.key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode()
        )
        self.directory, self.requests = directory, []
        owner = self

        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append(self.path)
                if self.path == "/FORBIDDEN-FULL-SETUP.exe":
                    self.send_error(500)
                    return
                super().do_GET()

            def log_message(self, *args):
                pass  # Never print tokens, headers or credentials.

        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(Handler, directory=str(directory))
        )
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def publish(self, archive: Path, base: str, version: str) -> dict:
        package = dict(
            from_version=base,
            url=self.url + "/" + archive.name,
            sha256=sha(archive),
            size=archive.stat().st_size,
        )
        doc = dict(
            schema_version=1,
            version=version,
            pub_date="2026-10-25T00:00:00Z",
            min_app_version="99.30.0",
            notes_fa="آزمایش خصوصی CI، نه انتشار: تأیید صریح پیش از دلتا لازم است.",
            full_installer=dict(
                url=self.url + "/FORBIDDEN-FULL-SETUP.exe", sha256="0" * 64, size=1000000000
            ),
            deltas=[package],
        )
        raw = (json.dumps(doc, ensure_ascii=False) + "\n").encode()
        (self.directory / "latest.json").write_bytes(raw)
        (self.directory / "latest.json.sig").write_bytes(self.key.sign(raw))
        return package

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)


def active_ready(home: Path, root: Path) -> tuple[dict, Path, dict]:
    active = read(home / "active-launch.json")
    if active["payload_root"] != str(root) or len(active["launch_id"]) != 32:
        raise ValueError("Foreign installed active process")
    folder = home / "state/launches" / active["launch_id"]
    return active, folder, read(folder / "ready.json")


def launch(root: Path, home: Path, env: dict, log: Path) -> tuple[subprocess.Popen, Path, dict]:
    with log.open("wb") as stream:
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
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    active = wait_file(home / "active-launch.json", process)
    folder = home / "state/launches" / active["launch_id"]
    ready = wait_file(folder / "ready.json", process)
    if active["payload_root"] != str(root):
        raise ValueError("Unexpected live app root")
    return process, folder, ready


def stop_owned(home: Path, root: Path) -> tuple[Path, dict]:
    active, folder, ready = active_ready(home, root)
    dump(folder / "stop.json", dict(pid=ready["pid"], launch_id=active["launch_id"]))
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if not (home / "active-launch.json").exists() and (folder / "completed.json").exists():
            done = read(folder / "completed.json")
            if (
                done["pid"] != ready["pid"]
                or not done["graceful_shutdown"]
                or not done["desktop_lock_released"]
            ):
                raise ValueError("Installed transaction process shutdown differs")
            return folder, done
        time.sleep(0.1)
    raise TimeoutError("Owned transaction app did not stop gracefully; no force-kill success")


def wait_terminal(client, home: Path, expected: str, old_attempt: str | None) -> tuple[dict, bool]:
    import httpx

    deadline, saw_gate = time.monotonic() + 240, False
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/v1/system/update/status")
            if response.status_code == 200:
                status = response.json()
                result = home / "state/data/updates/last-result.json"
                current = read(result) if result.exists() else {}
                if (
                    status["state"] in ("committed", "rolled_back", "failed")
                    and current.get("attempt_id") != old_attempt
                ):
                    if status["state"] != expected or status["verified"] is not (
                        expected == "committed"
                    ):
                        raise ValueError("Actual native update terminal result differs")
                    if any(
                        p.exists()
                        for p in (
                            home / ".native-channel.lock",
                            home / ".native-update.lock",
                            home / "state/data/updates/.update.lock",
                        )
                    ):
                        raise ValueError("Terminal result returned before cleanup")
                    return status, saw_gate
                # Deliberately invalid business request: cannot create rows if
                # admitted; lets a real HTTP observer see the write quarantine.
                probe = client.post("/api/v1/orders", json={})
                if probe.status_code == 503:
                    if (
                        probe.json().get("code") != "update_in_progress"
                        or probe.headers.get("Retry-After") != "3"
                    ):
                        raise ValueError("Actual write quarantine response differs")
                    saw_gate = True
                elif probe.status_code not in (422,):
                    raise ValueError("Unexpected invalid-write response during native update")
        except (httpx.TransportError, FileNotFoundError):
            pass  # A real process replacement necessarily interrupts TCP.
        time.sleep(0.05)
    raise TimeoutError("Real native update did not reach a fresh verified terminal result")


def _run_owned(
    root: Path,
    profile: Path,
    reports: Path,
    baseline_audit: Path,
    target_candidate: Path,
    target_audit: Path,
    target_helper: Path,
    environment: dict,
    password: str,
    sessions: dict,
) -> dict:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Disposable Windows CI real native transaction only")
    runner = Path(os.environ["RUNNER_TEMP"])
    for p in (root, profile, target_candidate, target_helper):
        if not p.is_absolute() or not p.is_relative_to(runner) or p == runner:
            raise ValueError("Disposable runner-owned transaction inputs required")
    a, b = read(baseline_audit), read(target_audit)
    variant = b["private_codegen_variant"]
    if (
        variant["baseline_audit_sha256"] != sha(baseline_audit)
        or not variant["native_executable_text_changed"]
        or a["preferred_source_trees"] != b["preferred_source_trees"]
        or a["dll_count"] != 21
        or b["dll_count"] != 21
    ):
        raise ValueError("Independent genuine native target proof differs")
    if sha(target_helper) == sha(root / "vira-updater.exe"):
        raise ValueError("Need distinct real helper bytes to prove EXE replacement")
    home, work = profile / "VIRA/private-native-installed", root.parent / "native-transaction-work"
    work.mkdir()
    feed_dir = work / "feed"
    feed_dir.mkdir()
    pin = read(home / "anchor.json")
    forward = work / "forward-target"
    forward_pin = target_payload(
        root, forward, target_candidate, target_audit, "99.30.1", target_helper, pin
    )
    # A newer app version with the independently audited ORIGINAL native closure
    # exercises genuine B->A native file operations, then forced verified rollback.
    reverse = work / "rollback-target"
    reverse_pin = target_payload(
        root,
        reverse,
        root / "native/pdf",
        baseline_audit,
        "99.30.2",
        root / "vira-updater.exe",
        pin,
    )
    forward_zip = packet(root, forward, forward_pin, feed_dir)
    forward_packet = check_packet(root, forward, forward_zip)
    reverse_zip = packet(forward, reverse, reverse_pin, feed_dir)
    reverse_packet = check_packet(forward, reverse, reverse_zip)
    import httpx

    results = {}
    with Feed(feed_dir) as feed:
        env = dict(
            environment, APP_UPDATE_URL=feed.url + "/latest.json", UPDATE_PUBLIC_KEY=feed.public
        )
        for key in (
            "VIRA_VERSION",
            "VIRA_APP_DIR",
            "VIRA_GIT_COMMIT",
            "VIRA_PRIVATE_UPDATE_TOKEN",
            "VIRA_PRIVATE_SOURCE_FORCE_FAILURE",
        ):
            env.pop(key, None)
        receipt_id = entry_id = None
        for name, archive, version, expected in [
            ("commit", forward_zip, "99.30.1", "committed"),
            ("rollback", reverse_zip, "99.30.2", "rolled_back"),
        ]:
            out = reports / ("native-" + name)
            out.mkdir()
            package = feed.publish(archive, read(root / "version.json")["version"], version)
            case_env = dict(env)
            if name == "rollback":
                case_env["VIRA_PRIVATE_SOURCE_FORCE_FAILURE"] = "AFTER_APPLY"
            process, _, ready = launch(root, home, case_env, out / "launcher.log")
            with httpx.Client(
                base_url=ready["url"], cookies=sessions, trust_env=False, timeout=10
            ) as client:
                checked(client.get("/api/v1/auth/me"), 200)
                client.headers.update(
                    {"X-CSRF-Token": sessions["vira_csrf"], "Origin": ready["url"]}
                )
                checked(
                    client.post(
                        "/api/v1/system/update/download",
                        json=dict(expected_version=version, expected_sha256=package["sha256"]),
                    ),
                    403,
                )
                sudo = checked(
                    client.post("/api/v1/auth/sudo", json={"password": password}), 200
                ).json()
                client.headers["X-Sudo-Token"] = sudo["sudo_token"]
                if name == "commit":
                    accounts = checked(client.get("/api/v1/accounts"), 200).json()
                    ids = [
                        x["id"]
                        for x in accounts
                        if not x["is_placeholder"] and x["currency"] == "IRR"
                    ][:2]
                    if len(ids) != 2:
                        raise ValueError("Two real seeded accounting accounts required")
                    payload = dict(
                        transaction_date="2026-10-25",
                        description="Synthetic CI native-update preservation",
                        splits=[
                            dict(account_id=ids[0], debit="1234567890.1000", currency="IRR"),
                            dict(account_id=ids[1], credit="1234567890.1000", currency="IRR"),
                        ],
                    )
                    entry_id = checked(
                        client.post("/api/v1/journal-entries", json=payload), 201
                    ).json()["id"]
                    checked(client.post(f"/api/v1/journal-entries/{entry_id}/post"), 200)
                    receipt = (reports / "first-installed-process/single-page.pdf").read_bytes()
                    receipt_id = checked(
                        client.post(
                            "/api/v1/documents/receipts",
                            files={"file": ("synthetic.pdf", receipt, "application/pdf")},
                            data={"journal_entry_id": entry_id},
                        ),
                        201,
                    ).json()["id"]
                discovery = checked(client.get("/api/v1/system/check-updates"), 200).json()
                if (
                    not discovery["checked"]
                    or discovery["manual_required"]
                    or discovery["choice"]["kind"] != "delta"
                    or discovery["latest"] != version
                ):
                    raise ValueError(
                        "Actual in-app discovery did not select the direct native delta"
                    )
                prior_status = checked(client.get("/api/v1/system/update/status"), 200).json()
                checked(
                    client.post(
                        "/api/v1/system/update/download",
                        json=dict(expected_version=version, expected_sha256="0" * 64),
                    ),
                    400,
                )
                if checked(client.get("/api/v1/system/update/status"), 200).json() != prior_status:
                    raise ValueError("Rejected approval still started a download")
                checked(
                    client.post(
                        "/api/v1/system/update/download",
                        json=dict(expected_version=version, expected_sha256=package["sha256"]),
                    ),
                    200,
                )
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    staged = checked(client.get("/api/v1/system/update/status"), 200).json()
                    if staged["state"] == "staged":
                        break
                    if staged["state"] == "failed":
                        raise ValueError("Ordinary streaming verifier rejected native delta")
                    time.sleep(0.1)
                else:
                    raise TimeoutError("Native delta download/staging deadline")
                if not staged["verified"] or staged["downloaded_bytes"] != package["size"]:
                    raise ValueError("Downloaded delta not byte-count/SHA verified")
                database = home / "state/data/data/vira.sqlite3"
                before = fingerprint(database)
                secret = sha(home / "state/session.secret")
                receipt_before = checked(
                    client.get(f"/api/v1/documents/receipts/{receipt_id}"), 200
                ).content
                entry_before = checked(
                    client.get(f"/api/v1/journal-entries/{entry_id}"), 200
                ).json()
                last = home / "state/data/updates/last-result.json"
                previous_attempt = read(last)["attempt_id"] if last.exists() else None
                checked(client.post("/api/v1/system/update/apply"), 200)
                terminal, saw_gate = wait_terminal(client, home, expected, previous_attempt)
                if process.wait(timeout=30) != 0:
                    raise ValueError("Old real app bridge exited abnormally")
                after_fingerprint = fingerprint(database)
                if after_fingerprint != before or sha(home / "state/session.secret") != secret:
                    raise ValueError(
                        "Accounting/IDs/security rows or session secret changed during native transaction"
                    )
                checked(client.get("/api/v1/auth/me"), 200)  # SAME cookie; no fresh login.
                if (
                    checked(client.get(f"/api/v1/journal-entries/{entry_id}"), 200).json()
                    != entry_before
                ):
                    raise ValueError("Posted accounting entry/scaled amounts/IDs changed")
                if (
                    checked(client.get(f"/api/v1/documents/receipts/{receipt_id}"), 200).content
                    != receipt_before
                ):
                    raise ValueError("Stored receipt changed during native transaction")
                # A healthy but slow real replacement may outlive the five-minute
                # sudo TTL. Re-elevate through the real password endpoint AFTER
                # full-DB/session/secret preservation was checked, never relogin or
                # extend/bypass the token. Its new audit row is legitimate activity.
                renewed = checked(
                    client.post("/api/v1/auth/sudo", json={"password": password}), 200
                ).json()
                client.headers["X-Sudo-Token"] = renewed["sudo_token"]
                current_version = checked(client.get("/api/v1/system/status"), 200).json()[
                    "version"
                ]
                if current_version != "99.30.1":
                    raise ValueError(
                        "Commit or verified rollback did not run expected installed version"
                    )
                expected_files = read(forward / "install_manifest.json")["files"]
                if sha(root / "install_manifest.json") != sha(
                    forward / "install_manifest.json"
                ) or read(home / "anchor.json") != read(forward_pin):
                    raise ValueError("Post-transaction manifest/independent anchor differs")
                if {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} != {
                    f["path"] for f in expected_files
                } | {"install_manifest.json"}:
                    raise ValueError("Unmanifested post-transaction installed file")
                for f in expected_files:
                    if sha(root / f["path"]) != f["sha256"]:
                        raise ValueError(
                            "Complete post-transaction installed file manifest differs"
                        )
                http = exercise_http(ready["url"], home / "state", out, password, True, sessions)
                _, _, new_ready = active_ready(home, root)
                folder, completed = stop_owned(home, root)
                events, peak = verify_events(folder / "pdf-lifecycles.jsonl", root)
                from desktop_launcher_probe import DIGITS

                documents = {
                    n: inspect_pdf(
                        (out / (n + ".pdf")).read_bytes(),
                        expected_by_weight={400: DIGITS, 700: "۰۱۲۳۴۵۶۷۸۹"},
                        min_pages=2 if "multi" in n else 1,
                    )
                    for n in http["documents"]
                }
                for n, d in documents.items():
                    if d["pages"] != (4 if "multi" in n else 1) or any(
                        d[k] != http["documents"][n][k] for k in ("sha256", "bytes")
                    ):
                        raise ValueError("Post-native PDF/HTTP bytes, fonts or pagination differ")
                if (
                    completed["qa_worker_executed"]
                    or completed["qa_factory_or_renderer_replacement"]
                    or completed["factory_module"] != "app.main"
                    or completed["renderer_module"] != "app.services.pdf_rendering"
                ):
                    raise ValueError("Native transaction did not preserve app-owned lifecycle")
                if any(
                    Path(path) != root / "native/pdf/bin" / n
                    for n, path in completed["loaded_dlls"].items()
                ):
                    raise ValueError("Actual restarted native DLL origin differs")
                if (
                    completed["activation"]["source_audit_sha256"] != sha(target_audit)
                    or completed["activation"]["dll_count"] != 21
                    or new_ready["pid"] == ready["pid"]
                ):
                    raise ValueError("Actual restarted target Source21 process origin differs")
                for filename in ("ready.json", "completed.json", "pdf-lifecycles.jsonl"):
                    shutil.copyfile(folder / filename, out / filename)
                stage = Path(staged["staged_path"])
                contexts = list(stage.parent.glob("private-transaction-*.json"))
                if len(contexts) != 1:
                    raise ValueError("Exactly one old-helper transaction context required")
                context = read(contexts[0])
                journal = read(Path(context["attempt"]) / "result.json")
                if (
                    journal["state"] != expected
                    or journal["database_fingerprint"] != before
                    or journal["archive_sha256"] != package["sha256"]
                ):
                    raise ValueError(
                        "Actual durable transaction journal differs from independent client"
                    )
                dump(out / "transaction-journal.json", journal)
                results[name] = dict(
                    discovery=discovery,
                    package=forward_packet if name == "commit" else reverse_packet,
                    terminal=terminal,
                    journal=journal,
                    sudo_refreshed_through_real_endpoint_after_preservation_check=True,
                    forced_failure_point="AFTER_FILE_APPLY_BEFORE_TARGET_STARTUP"
                    if name == "rollback"
                    else None,
                    old_pid=ready["pid"],
                    new_pid=new_ready["pid"],
                    database_fingerprint_before=before,
                    database_fingerprint_after=after_fingerprint,
                    full_database_preserved=True,
                    persistent_session_accepted_without_login=True,
                    persistent_secret_preserved=True,
                    receipt_bytes_preserved=True,
                    posted_entry_preserved=True,
                    write_quarantine_http503_observed=saw_gate,
                    http=http,
                    completed=completed,
                    documents=documents,
                    font_documents=events,
                    peak_concurrent_documents=peak,
                )
    if "/FORBIDDEN-FULL-SETUP.exe" in feed.requests:
        raise ValueError("Routine update tried downloading full setup")
    result = dict(
        role="PHASE3_REAL_IN_APP_SOURCE21_NATIVE_DELTA_AND_FORCED_ROLLBACK_PRIVATE_NOT_RELEASE",
        baseline_audit_sha256=sha(baseline_audit),
        target_audit_sha256=sha(target_audit),
        target_codegen=variant,
        cases=results,
        requests=feed.requests,
        full_setup_requested=False,
        real_native_delta_and_forced_rollback=True,
        crash_recovery_proven=False,
        phase3_complete=False,
        release_authorized=False,
    )
    dump(reports / "verified-native-transaction.json", result)
    return result


def collect_failure_diagnostics(home: Path, reports: Path, runner: Path) -> None:
    """Read only bounded, fixed startup logs; NEVER collect DB/secrets/packages.

    A context may not redirect diagnostics outside its exact nonce-owned attempt.
    This is diagnostics, not recovery or permission to remove any guard.
    """
    def safe(path: Path) -> None:
        for part in (path, *path.parents):
            if part.is_symlink() or (
                part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("Diagnostic reparse path rejected")

    updates = home / "state/data/updates"
    safe(updates)
    out = reports / "failure-diagnostics"
    out.mkdir(exist_ok=True)
    guards = [home / ".native-channel.lock", home / ".native-update.lock",
              updates / ".update.lock"]
    summary = dict(guards_present=[p.exists() for p in guards], startup_logs=[])
    contexts = sorted(updates.glob("*/*/private-transaction-*.json"))
    for context in contexts[:8]:
        safe(context)
        if context.stat().st_size > 65536:
            continue
        nonce = context.stem.removeprefix("private-transaction-")
        if len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
            continue
        value = read(context)
        attempt = runner / ("VIRA تراکنش خصوصی ! & " + nonce)
        if (value.get("role") != "PRIVATE_SOURCE_TRANSACTION"
                or value.get("attempt") != str(attempt)):
            continue
        safe(attempt)
        for name in ("target-startup.log", "rollback-startup.log"):
            log = attempt / name
            safe(log)
            if not log.is_file():
                continue
            with log.open("rb") as stream:
                size = stream.seek(0, 2)
                stream.seek(max(0, size - 16384))
                tail = stream.read(16384)
            destination = out / (nonce + "-" + name)
            destination.write_bytes(tail)
            summary["startup_logs"].append(dict(
                file=destination.name, complete_bytes=size, tail_bytes=len(tail),
                tail_sha256=hashlib.sha256(tail).hexdigest(),
            ))
    dump(out / "snapshot.json", summary)


def run(
    root: Path,
    profile: Path,
    reports: Path,
    baseline_audit: Path,
    target_candidate: Path,
    target_audit: Path,
    target_helper: Path,
    environment: dict,
    password: str,
    sessions: dict,
) -> dict:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Disposable Windows CI real native transaction only")
    runner = Path(os.environ["RUNNER_TEMP"])
    for p in (root, profile, target_candidate, target_helper):
        if not p.is_absolute() or ".." in p.parts or not p.is_relative_to(runner) or p == runner:
            raise ValueError("Disposable runner-owned transaction inputs required")
        for part in (p, *p.parents):
            if part.is_symlink() or (
                part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("Transaction client reparse path rejected")
    if environment.get("LOCALAPPDATA") != str(profile):
        raise ValueError("Transaction client profile differs from process environment")
    try:
        return _run_owned(
            root,
            profile,
            reports,
            baseline_audit,
            target_candidate,
            target_audit,
            target_helper,
            environment,
            password,
            sessions,
        )
    except BaseException:
        # Diagnostics may fail closed, but must never replace the real error.
        with suppress(OSError, ValueError, KeyError, TypeError):
            collect_failure_diagnostics(profile / "VIRA/private-native-installed", reports, runner)
        raise
    finally:
        # Never interfere with an in-flight helper or erase its recovery guards.
        # A failed proof is NOT success merely because CI eventually kills orphans.
        home = profile / "VIRA/private-native-installed"
        guards = (
            home / ".native-channel.lock",
            home / ".native-update.lock",
            home / "state/data/updates/.update.lock",
        )
        if (home / "active-launch.json").exists() and not any(p.exists() for p in guards):
            stop_owned(home, root)

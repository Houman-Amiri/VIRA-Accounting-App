"""Windows CI ONLY: real browser -> API -> streamed ZIP -> source PS helper -> restart.

Versions 99.0.x are private fixtures of CURRENT code, NOT published 1.0.6 clients.
The source helper is used to avoid substituting a dummy process for real apply;
compiled-helper compatibility remains a separate release dry-run requirement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.update_database import fingerprint  # noqa: E402


def run(*args: str, **kwargs) -> None:
    subprocess.run(list(args), check=True, timeout=180, **kwargs)


def port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def seed_business() -> None:
    """Dedicated disposable fixture with a posted ledger and a completed order."""
    if os.environ.get("VIRA_E2E_DISPOSABLE_DATABASE") != "1":
        raise RuntimeError("refusing to seed without disposable database acknowledgement")
    from app.config import load_settings
    from app.db import Database
    from app.schemas.ledger import AccountCreate, JournalEntryCreate, SplitCreate
    from app.schemas.operations import (
        InventoryItemCreate,
        OrderCreate,
        OrderItemIn,
        ProductionJobCreate,
    )
    from app.services.ledger import LedgerService
    from app.services.operations import OperationsService

    database = Database(load_settings())
    try:
        with database.session() as session:
            ledger = LedgerService(session)
            cash = ledger.create_account(
                AccountCreate(code="990101", name="native cash", account_type="ASSET")
            )
            equity = ledger.create_account(
                AccountCreate(code="990301", name="native capital", account_type="EQUITY")
            )
            entry = ledger.create_draft(
                JournalEntryCreate(
                    transaction_date="2026-10-16",
                    description="native posted exact amount",
                    splits=[
                        SplitCreate(account_id=cash.id, debit="123456789.1234"),
                        SplitCreate(account_id=equity.id, credit="123456789.1234"),
                    ],
                )
            )
            ledger.post(entry.id)
            ops = OperationsService(session)
            filament = ops.create_item(
                InventoryItemCreate(
                    name="native filament",
                    kind="FILAMENT",
                    unit="G",
                    quantity="1000",
                    unit_price="100",
                )
            )
            product = ops.create_item(
                InventoryItemCreate(name="native model", kind="PRODUCT", unit="PCS")
            )
            order = ops.create_order(
                OrderCreate(
                    order_date="2026-10-16",
                    customer_name="native customer",
                    items=[
                        OrderItemIn(
                            product_name="native model",
                            quantity="2",
                            unit_price="123.4567",
                            unit_cost="23.4567",
                        )
                    ],
                )
            )
            job = ops.create_job(
                ProductionJobCreate(
                    product_name="native model",
                    quantity="2",
                    filament_grams="12.5",
                    filament_item_id=filament.id,
                    product_item_id=product.id,
                    order_id=order.id,
                    order_item_id=order.items[0].id,
                    unit_price="123.4567",
                    unit_cost="23.4567",
                )
            )
            ops.finish_job(job.id)
    finally:
        database.dispose()


# Pinned public asset digest from GitHub release v1.0.9; not a rebuilt baseline.
LEGACY_SHA256 = "5b5ddba7656a35c7ab14d2f92d0d0263f442f1d1890d4ba74e1d27e632928e16"


def emit_diagnostic(path: Path) -> None:
    """Keep all failure evidence even on Windows' legacy stdout code page."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")[-2300:]
    escaped = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    # ASCII transport preserves non-ASCII characters as explicit escapes. A
    # Persian startup path must not crash reporting before server.log is read.
    annotation = f"::error title=phase8 {path.name}::{escaped}"
    print(annotation.encode("ascii", errors="backslashreplace").decode("ascii"), flush=True)


def verify_payload(root: Path, *, runtime: bool = False) -> None:
    """Check shipped file bytes, excluding mutable Python caches only after boot."""
    manifest = json.loads((root / "install_manifest.json").read_text(encoding="utf-8-sig"))
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if (
            relative.anchor
            or ".." in relative.parts
            or ":" in entry["path"]
            or "\\" in entry["path"]
        ):
            raise ValueError("unsafe payload manifest path")
        if runtime and ("__pycache__" in relative.parts or relative.suffix == ".pyc"):
            continue
        file = root / relative
        if not file.is_file() or sha(file) != entry["sha256"]:
            raise ValueError(f"payload file hash mismatch: {relative}")


@dataclass(frozen=True)
class PublishedUpgrade:
    base: Path
    packages: Path
    base_version: str = "1.0.9"
    target_version: str = "1.0.10"
    base_commit: str = "7d78720"
    archive_sha256: str = LEGACY_SHA256
    schema_rollback: bool = False

    @property
    def delta_name(self) -> str:
        return f"VIRA-v{self.target_version}-delta-from-v{self.base_version}.zip"

    def validate(self) -> None:
        archive = self.base.parent / f"base-{self.base_version}.zip"
        if sha(archive) != self.archive_sha256:
            raise ValueError("published ZIP digest mismatch")
        stamp = json.loads((self.base / "version.json").read_text(encoding="utf-8-sig"))
        if stamp["version"] != self.base_version or not stamp["commit"].startswith(
            self.base_commit
        ):
            raise ValueError("not the pinned immutable published client")
        verify_payload(self.base)
        target = json.loads((self.packages / "app/version.json").read_text(encoding="utf-8-sig"))
        if target["version"] != self.target_version:
            raise ValueError("candidate version mismatch")
        if not (self.packages / self.delta_name).is_file():
            raise ValueError("mandatory direct delta missing")


def published_fixture(
    root: Path, rollback: bool, published: PublishedUpgrade
) -> tuple[Path, Path, Path]:
    install = root / "install with spaces"
    # No source replacement, bootstrap injection or patched launcher in the base.
    shutil.copytree(published.base, install)
    archive = published.packages / published.delta_name
    if rollback and not published.schema_rollback:
        # Separate private broken target; never replace the candidate ZIP.
        target = root / "intentionally broken target"
        shutil.copytree(published.packages / "app", target)
        (target / "app/main.py").write_text(
            'raise RuntimeError("intentional legacy readiness failure")\n'
        )
        run(
            sys.executable,
            str(ROOT / "scripts/gen_delta.py"),
            "--base-manifest",
            str(install / "install_manifest.json"),
            "--base-dir",
            str(install),
            "--target-dir",
            str(target),
            "--base-version",
            published.base_version,
            "--target-version",
            published.target_version,
            "--out",
            str(root),
        )
        archive = root / archive.name
    return install, install / "start_vira.cmd", archive


def source_fixture(root: Path, rollback: bool) -> tuple[Path, Path, Path]:
    install, target = root / "install with spaces", root / "target"
    install.mkdir(parents=True)
    shutil.copytree(
        ROOT / "backend/app", install / "app", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(ROOT / "frontend/dist", install / "static")
    (install / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/update_database.py", install / "scripts/update_database.py")
    (install / "version.json").write_text(
        json.dumps(dict(version="99.0.0", commit="native-old", spa_build="native-old"))
    )
    index = install / "static/index.html"
    index.write_text(
        re.sub(
            r'(name="vira-build"\s+content=")[^"]+',
            r"\g<1>native-old",
            index.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    (install / "static/delete-me.txt").write_text("restore this deleted file")
    (install / "static/replaced.txt").write_text("old bytes")
    (install / "vira-updater.exe").write_bytes(b"MZ-source-helper-fixture-not-executed")
    bootstrap = install / "bootstrap.py"
    bootstrap.write_text(f"""import os
from pathlib import Path
from app.services import update
import uvicorn
update._updater_command = lambda settings, stage: (["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", {str(ROOT / "scripts/vira_updater.ps1")!r}, "-Stage", stage, "-Log", str(Path(stage)/"update.log"), "-InstallDir", {str(install)!r}, "-HealthTimeoutSeconds", "15"], Path(stage)/"update.log")
uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ["VIRA_PORT"]))
""")
    (install / "start_vira.cmd").write_text(
        f'@echo off\r\ncd /d "%~dp0"\r\n"{sys.executable}" "{bootstrap}" >> "{root / "server.log"}" 2>&1\r\n'
    )
    run(
        sys.executable,
        str(ROOT / "scripts/build_manifest.py"),
        str(install),
        "-o",
        str(install / "install_manifest.json"),
    )
    shutil.copytree(install, target)
    (target / "version.json").write_text(
        json.dumps(dict(version="99.0.1", commit="native-new", spa_build="native-new"))
    )
    (target / "static/index.html").write_text(
        index.read_text(encoding="utf-8").replace("native-old", "native-new"), encoding="utf-8"
    )
    (target / "static/delete-me.txt").unlink()
    (target / "static/replaced.txt").write_text("new bytes")
    (target / "static/added.txt").write_text("remove this on rollback")
    if rollback:
        (target / "app/main.py").write_text(
            'raise RuntimeError("intentional native readiness failure")\n'
        )
    run(
        sys.executable,
        str(ROOT / "scripts/gen_delta.py"),
        "--base-manifest",
        str(install / "install_manifest.json"),
        "--base-dir",
        str(install),
        "--target-dir",
        str(target),
        "--base-version",
        "99.0.0",
        "--target-version",
        "99.0.1",
        "--out",
        str(root),
    )
    return install, bootstrap, next(root.glob("*.zip"))


def scenario(root: Path, rollback: bool, published: PublishedUpgrade | None = None) -> None:
    root.mkdir(parents=True)
    data = root / "user-data"
    data.mkdir()
    if published:
        install, bootstrap, archive = published_fixture(root, rollback, published)
        old_version, new_version = published.base_version, published.target_version
    else:
        install, bootstrap, archive = source_fixture(root, rollback)
        old_version, new_version = "99.0.0", "99.0.1"
    database = data / "vira.sqlite3"
    env = {
        **os.environ,
        "DATA_DIR": str(data),
        "SQLITE_DATABASE_PATH": str(database),
        "ENVIRONMENT": "development",
        "SESSION_SECRET": secrets.token_urlsafe(48),
    }
    # Seed genuine schema/chart/owner + persisted operational data, not an empty DB.
    password = secrets.token_urlsafe(24)
    if published and published.schema_rollback:
        # The installed public client must start on ITS revision and use ITS ORM,
        # never the newer source migrator/models before the upgrade under test.
        baseline_env = {**env, "PYTHONPATH": str(install)}
        run(sys.executable, str(install / "scripts/migrate_vira.py"), "--database", str(database), env=baseline_env, cwd=install)
        run(sys.executable, "-m", "app.seed", env={**baseline_env, "VIRA_ADMIN_PASSWORD": password}, cwd=install)
        run(sys.executable, "-c", f"import sys;sys.path.insert(0,{str(ROOT)!r});from scripts.update_native_smoke import seed_business;sys.path.insert(0,{str(install)!r});seed_business()", env={**baseline_env, "VIRA_E2E_DISPOSABLE_DATABASE":"1"}, cwd=install)
        with closing(sqlite3.connect(database)) as old_db:
            assert old_db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005_pricing_settings"
            assert old_db.execute("SELECT count(*) FROM sqlite_master WHERE name='item_types'").fetchone()[0] == 0
    else:
        run(sys.executable, str(ROOT / "scripts/migrate_vira.py"), "--database", str(database), env=env)
        run(sys.executable, "-m", "app.seed", env={**env, "VIRA_ADMIN_PASSWORD": password})
        run(sys.executable, "-c", "from scripts.update_native_smoke import seed_business; seed_business()", env={**env, "VIRA_E2E_DISPOSABLE_DATABASE": "1"})
    with closing(sqlite3.connect(database)) as db:
        db.execute("CREATE TABLE phase8_sentinel(value TEXT NOT NULL)")
        db.execute("INSERT INTO phase8_sentinel VALUES ('exact business data 123.4567')")
        db.commit()
    receipt = data / "receipt_storage/sentinel.bin"
    receipt.parent.mkdir(exist_ok=True)
    receipt.write_bytes(secrets.token_bytes(2048))
    receipt_hash = sha(receipt)
    checkpoint_hash = None
    checkpoint_fingerprint = None
    if published and published.schema_rollback:
        env["VIRA_SCHEMA_PROOF_REPORT"] = str(root / "migration-proof.json")
    counts = dict(delta=0, full=0)

    class Feed(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            nonlocal checkpoint_hash, checkpoint_fingerprint
            assert self.path == "/checkpoint"
            with closing(sqlite3.connect(database)) as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            checkpoint_hash = sha(database)

            checkpoint_fingerprint = fingerprint(database)
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            if self.path == "/latest.json":
                body = json.dumps(
                    dict(
                        schema_version=1,
                        pub_date="2026-10-16T00:00:00Z",
                        version=new_version,
                        min_app_version=old_version,
                        full_installer=dict(
                            url=feed_url + "/setup.exe", sha256="00" * 32, size=100_000_000
                        ),
                        deltas=[
                            dict(
                                from_version=old_version,
                                url=feed_url + "/delta.zip",
                                sha256=sha(archive),
                                size=archive.stat().st_size,
                            )
                        ],
                        notes_fa="آزمون خصوصی فاز ۸",
                        notes_en="Private fixture",
                    )
                ).encode()
            elif self.path == "/delta.zip":
                counts["delta"] += 1
                body = archive.read_bytes()
            elif self.path == "/setup.exe":
                counts["full"] += 1
                body = b"FORBIDDEN FULL INSTALLER"
            elif self.path == "/attempt-result":
                result = data / "updates/last-result.json"
                body = result.read_bytes() if result.is_file() else b'{"state":"pending"}'
            elif self.path == "/counts":
                body = json.dumps(counts).encode()
            elif self.path == "/verify-data":
                try:
                    with closing(sqlite3.connect(database)) as db:
                        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
                        assert (
                            db.execute("SELECT value FROM phase8_sentinel").fetchone()[0]
                            == "exact business data 123.4567"
                        )
                        assert (
                            db.execute(
                                "SELECT count(*) FROM journal_entries WHERE status='POSTED'"
                            ).fetchone()[0]
                            == 1
                        )
                        assert (
                            db.execute(
                                "SELECT count(*) FROM production_jobs WHERE status='DONE'"
                            ).fetchone()[0]
                            == 1
                        )
                        assert (
                            db.execute(
                                "SELECT count(*) FROM orders WHERE status='READY'"
                            ).fetchone()[0]
                            == 1
                        )
                        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    if published and published.schema_rollback:
                        proof = json.loads((root / "migration-proof.json").read_text())
                        assert proof["revision"] == "0006_item_catalog", proof
                        assert proof["new_table"] is True, proof
                        assert fingerprint(database) == checkpoint_fingerprint, (
                            "restored schema/data mismatch"
                        )
                        with closing(sqlite3.connect(database)) as old_db:
                            assert (
                                old_db.execute(
                                    "SELECT version_num FROM alembic_version"
                                ).fetchone()[0]
                                == "0005_pricing_settings"
                            )
                            assert (
                                old_db.execute(
                                    "SELECT count(*) FROM sqlite_master WHERE name='item_types'"
                                ).fetchone()[0]
                                == 0
                            )
                        failed = list(
                            data.rglob("database-rollback/failed-database/database.sqlite3")
                        )
                        assert len(failed) == 1, "failed target DB not retained"
                        with closing(sqlite3.connect(failed[0])) as failed_db:
                            assert (
                                failed_db.execute(
                                    "SELECT version_num FROM alembic_version"
                                ).fetchone()[0]
                                == "0006_item_catalog"
                            )
                    else:
                        assert checkpoint_hash is not None and sha(database) == checkpoint_hash, (
                            "SQLite hash changed"
                        )
                    assert sha(receipt) == receipt_hash, "receipt hash changed"
                    body = b"verified SQLite schema/data and receipt hash"
                except Exception as exc:
                    self.send_error(500, str(exc))
                    return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    feed = ThreadingHTTPServer(("127.0.0.1", 0), Feed)
    feed_url = f"http://127.0.0.1:{feed.server_port}"
    thread = threading.Thread(target=feed.serve_forever, daemon=True)
    thread.start()
    app_port = port()
    url = f"http://127.0.0.1:{app_port}"
    env.update(
        VIRA_PORT=str(app_port),
        BIND_PORT=str(app_port),
        VIRA_APP_DIR=str(install),
        APP_UPDATE_URL=feed_url + "/latest.json",
        PYTHONPATH=str(install),
    )
    if published:
        # The released launcher uses LOCALAPPDATA as well as DATA_DIR. Both are
        # disposable; never reuse the runner's ordinary VIRA profile.
        # Playwright's installation stays in the runner's real cache, even
        # though the product and its default Edge opener use an isolated profile.
        env.setdefault(
            "PLAYWRIGHT_BROWSERS_PATH", str(Path(os.environ["LOCALAPPDATA"]) / "ms-playwright")
        )
        env["LOCALAPPDATA"] = str(root / "local profile")
        Path(env["LOCALAPPDATA"]).mkdir()
    # Ensure the repo's external environment cannot stamp our private fixture.
    for name in ("VIRA_VERSION", "VIRA_GIT_COMMIT", "VIRA_SPA_BUILD"):
        env.pop(name, None)
    browser_pids = ""
    if published:
        browser_pids = (
            subprocess.check_output(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "$ErrorActionPreference='Stop'; @(Get-Process -Name msedge -ErrorAction SilentlyContinue) | ForEach-Object { $_.Id }; exit 0",
                ],
                text=True,
            )
            .strip()
            .replace("\n", ",")
            .replace("\r", "")
        )
    log = (root / "initial-server.log").open("w")
    argv = (
        ["cmd.exe", "/d", "/c", "start_vira.cmd"] if published else [sys.executable, str(bootstrap)]
    )
    server = subprocess.Popen(
        argv, cwd=install, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
    )
    try:
        for _ in range(120):
            try:
                if httpx.get(url + "/api/v1/health/ready", timeout=1).json()["status"] == "ready":
                    break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("initial fixture server never became ready")
        run(
            "node",
            str(ROOT / "scripts/audit_in_app_update.cjs"),
            env={
                **env,
                "VIRA_NATIVE_BASE": url,
                "VIRA_NATIVE_FEED": feed_url,
                "VIRA_NATIVE_PASSWORD": password,
                "VIRA_NATIVE_EXPECTED": "rolled_back" if rollback else "committed",
                "VIRA_NATIVE_TARGET": new_version,
                "VIRA_NATIVE_LEGACY": "1" if published else "0",
                "VIRA_NATIVE_BASE_VERSION": old_version,
                "VIRA_NATIVE_BASE_COMMIT": published.base_commit if published else "native-old",
            },
        )
        if published:
            verify_payload(install, runtime=True)
            stamp = json.loads((install / "version.json").read_text(encoding="utf-8-sig"))
            assert stamp["version"] == (old_version if rollback else new_version)
        elif rollback:
            assert (install / "static/delete-me.txt").read_text() == "restore this deleted file"
            assert not (install / "static/added.txt").exists()
            assert (install / "static/replaced.txt").read_text() == "old bytes"
        else:
            assert not (install / "static/delete-me.txt").exists()
            assert (install / "static/added.txt").is_file()
            assert (install / "static/replaced.txt").read_text() == "new bytes"
        result = json.loads((data / "updates/last-result.json").read_text(encoding="utf-8-sig"))
        assert result["state"] == ("rolled_back" if rollback else "committed")
        assert list((data / "backups").glob("pre-update-*.sqlite3")), "pre-update backup missing"
    except Exception:
        for diagnostic in [
            *root.rglob("update.log"),
            *root.rglob("last-result.json"),
            *root.glob("*server.log"),
        ]:
            emit_diagnostic(diagnostic)
        raise
    finally:
        # Stop only this fixture's listener; never touch another VIRA installation.
        command = f"Get-NetTCPConnection -LocalPort {app_port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {{ $p = Get-Process -Id $_ -ErrorAction SilentlyContinue; if ($p) {{ Stop-Process -Id $p.Id -Force; if (-not $p.WaitForExit(10000)) {{ throw 'fixture process still alive' }} }} }}"
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command], check=True, timeout=30
        )
        if server.poll() is None:
            server.terminate()  # our initial cmd can remain at its old :fail pause
        server.wait(timeout=20)
        if published:
            # The production cmd's :fail pause can outlive its stopped Python.
            # Only helper-started launchers containing THIS unique install path.
            command = f"$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | Where-Object {{ $_.CommandLine -and $_.CommandLine.IndexOf('{install}', [StringComparison]::OrdinalIgnoreCase) -ge 0 }} | ForEach-Object {{ $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; if ($p -and -not $p.HasExited) {{ $null = $p.Handle; Stop-Process -InputObject $p -Force -ErrorAction SilentlyContinue; if (-not $p.WaitForExit(10000)) {{ throw 'fixture launcher still alive' }} }} }}; exit 0"
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command], check=True, timeout=30
            )
            # The genuine launcher opens the default Edge, separately from our
            # Playwright browser. Close ONLY new fixture-era Edge processes so
            # they cannot retain this disposable LOCALAPPDATA after teardown.
            command = f"$ErrorActionPreference='Stop'; $before = @({browser_pids}); Get-Process -Name msedge -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -notin $before }} | ForEach-Object {{ $p = $_; if (-not $p.HasExited) {{ $null = $p.Handle; Stop-Process -InputObject $p -Force -ErrorAction SilentlyContinue; if (-not $p.WaitForExit(10000)) {{ throw 'fixture browser still alive' }} }} }}; exit 0"
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command], check=True, timeout=30
            )
        log.close()
        feed.shutdown()
        feed.server_close()


if __name__ == "__main__":
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Refusing: isolated Windows GitHub Actions runner required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--published-base", type=Path)
    parser.add_argument("--packages", type=Path)
    parser.add_argument("--target-version", default=os.environ.get("VIRA_VERSION") or PublishedUpgrade.target_version)
    args = parser.parse_args()
    published = None
    if args.published_base or args.packages:
        if not args.published_base or not args.packages:
            parser.error("both --published-base and --packages are required")
        published = PublishedUpgrade(
            args.published_base.resolve(), args.packages.resolve(), target_version=args.target_version
        )
        published.validate()
    with tempfile.TemporaryDirectory(prefix="vira-in-app-", dir=os.environ["RUNNER_TEMP"]) as tmp:
        scenario(Path(tmp) / "success", False, published)
        scenario(Path(tmp) / "rollback", True, published)
    print(
        f"Published {published.base_version} client -> candidate {published.target_version} PASS"
        if published
        else "Native in-app consent/download/apply/restart and real rollback PASS; private current-code fixtures only"
    )

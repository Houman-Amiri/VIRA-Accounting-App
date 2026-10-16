"""Windows CI ONLY: real browser -> API -> streamed ZIP -> source PS helper -> restart.

Versions 99.0.x are private fixtures of CURRENT code, NOT published 1.0.6 clients.
The source helper is used to avoid substituting a dummy process for real apply;
compiled-helper compatibility remains a separate release dry-run requirement.
"""

from __future__ import annotations

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, **kwargs) -> None:
    subprocess.run(list(args), check=True, timeout=180, **kwargs)


def port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def scenario(root: Path, rollback: bool) -> None:
    install, target, data = root / "install with spaces", root / "target", root / "user-data"
    install.mkdir(parents=True)
    data.mkdir()
    shutil.copytree(
        ROOT / "backend/app", install / "app", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(ROOT / "frontend/dist", install / "static")
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
    archive = next(root.glob("*.zip"))
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
    run(sys.executable, str(ROOT / "scripts/migrate_vira.py"), "--database", str(database), env=env)
    run(sys.executable, "-m", "app.seed", env={**env, "VIRA_ADMIN_PASSWORD": password})
    run(
        sys.executable,
        "-c",
        "from scripts.update_native_smoke import seed_business; seed_business()",
        env={**env, "VIRA_E2E_DISPOSABLE_DATABASE": "1"},
    )
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE phase8_sentinel(value TEXT NOT NULL)")
        db.execute("INSERT INTO phase8_sentinel VALUES ('exact business data 123.4567')")
    receipt = data / "receipt_storage/sentinel.bin"
    receipt.parent.mkdir(exist_ok=True)
    receipt.write_bytes(secrets.token_bytes(2048))
    receipt_hash = sha(receipt)
    checkpoint_hash = None
    counts = dict(delta=0, full=0)

    class Feed(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            nonlocal checkpoint_hash
            assert self.path == "/checkpoint"
            with sqlite3.connect(database) as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            checkpoint_hash = sha(database)
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            if self.path == "/latest.json":
                body = json.dumps(
                    dict(
                        schema_version=1,
                        pub_date="2026-10-16T00:00:00Z",
                        version="99.0.1",
                        min_app_version="99.0.0",
                        full_installer=dict(
                            url=feed_url + "/setup.exe", sha256="00" * 32, size=100_000_000
                        ),
                        deltas=[
                            dict(
                                from_version="99.0.0",
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
            elif self.path == "/counts":
                body = json.dumps(counts).encode()
            elif self.path == "/verify-data":
                try:
                    with sqlite3.connect(database) as db:
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
                    assert checkpoint_hash is not None and sha(database) == checkpoint_hash, (
                        "SQLite hash changed"
                    )
                    assert sha(receipt) == receipt_hash, "receipt hash changed"
                    body = b"unchanged SQLite and receipt hashes"
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
    # Ensure the repo's external environment cannot stamp our private fixture.
    for name in ("VIRA_VERSION", "VIRA_GIT_COMMIT", "VIRA_SPA_BUILD"):
        env.pop(name, None)
    log = (root / "initial-server.log").open("w")
    server = subprocess.Popen(
        [sys.executable, str(bootstrap)], cwd=install, env=env, stdout=log, stderr=subprocess.STDOUT
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
            },
        )
        if rollback:
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
            text = diagnostic.read_text(encoding="utf-8-sig", errors="replace")[-2300:]
            # Actions annotations are bounded; emit each diagnostic separately
            # so an earlier startup transcript cannot hide the rollback reason.
            escaped = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=phase8 {diagnostic.name}::{escaped}", flush=True)
        raise
    finally:
        # Stop only this fixture's listener; never touch another VIRA installation.
        command = f"Get-NetTCPConnection -LocalPort {app_port} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command], check=False, timeout=30
        )
        server.wait(timeout=20)
        log.close()
        feed.shutdown()


if __name__ == "__main__":
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Refusing: isolated Windows GitHub Actions runner required")
    with tempfile.TemporaryDirectory(prefix="vira-in-app-") as tmp:
        scenario(Path(tmp) / "success", False)
        scenario(Path(tmp) / "rollback", True)
    print(
        "Native in-app consent/download/apply/restart and real rollback PASS; private current-code fixtures only"
    )

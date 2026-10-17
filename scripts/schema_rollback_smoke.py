"""CI-only: pinned public 1.0.10 -> final catalog DDL -> failure -> full DB rollback.

The candidate is private, but its migration and atomic runner are the production
source files, not a synthetic probe. No release, tag, base patch or user DB.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.update_native_smoke import PublishedUpgrade, run, scenario, sha  # noqa: E402

DIGEST = "73c36ae9a24fab4590b24f8af7343aeaab6b4c7f19c1f2cd38dd6db88e19fb97"
FAILURE = """import json, os, sqlite3
from pathlib import Path
with sqlite3.connect(os.environ['SQLITE_DATABASE_PATH']) as db:
    proof = dict(revision=db.execute('SELECT version_num FROM alembic_version').fetchone()[0],new_table=bool(db.execute("SELECT COUNT(*) FROM item_types").fetchone()[0]))
assert proof['revision'] == '0006_item_catalog', proof
with sqlite3.connect(os.environ['SQLITE_DATABASE_PATH']) as db:
    assert db.execute('SELECT COUNT(*) FROM item_types').fetchone()[0] == 2
    assert db.execute('SELECT COUNT(*) FROM item_units').fetchone()[0] == 2
    assert {'kind','unit','supplier_id'} <= {row[3] for row in db.execute('PRAGMA foreign_key_list(inventory_items)')}
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
Path(os.environ['VIRA_SCHEMA_PROOF_REPORT']).write_text(json.dumps(proof))
raise RuntimeError('intentional failure AFTER real schema migration')
"""


def main() -> None:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("isolated Windows CI runner required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    args = parser.parse_args()
    if sha(args.archive) != DIGEST:
        raise ValueError("immutable published 1.0.10 digest mismatch")
    with tempfile.TemporaryDirectory(
        prefix="vira-schema-gate-", dir=os.environ["RUNNER_TEMP"]
    ) as tmp:
        root = Path(tmp)
        shutil.copy2(args.archive, root / "base-1.0.10.zip")
        base = root / "public-1.0.10"
        with zipfile.ZipFile(args.archive) as z:
            z.extractall(base)  # exact pinned trusted ZIP
        packages = root / "private-candidate"
        target = packages / "app"
        shutil.copytree(base, target)
        shutil.copy2(args.helper, target / "vira-updater.exe")
        shutil.copy2(ROOT / "scripts/update_database.py", target / "scripts/update_database.py")
        import json

        stamp = json.loads((target / "version.json").read_text(encoding="utf-8-sig"))
        stamp["version"] = "99.0.1"
        (target / "version.json").write_text(json.dumps(stamp), encoding="utf-8")
        shutil.copy2(ROOT / "backend/alembic/versions/0006_item_catalog.py", target / "backend/alembic/versions/0006_item_catalog.py")
        shutil.copy2(ROOT / "backend/alembic/env.py", target / "backend/alembic/env.py")
        (target / "app/main.py").write_text(FAILURE)
        run(
            sys.executable,
            str(ROOT / "scripts/gen_delta.py"),
            "--base-manifest",
            str(base / "install_manifest.json"),
            "--base-dir",
            str(base),
            "--target-dir",
            str(target),
            "--base-version",
            "1.0.10",
            "--target-version",
            "99.0.1",
            "--out",
            str(packages),
        )
        published = PublishedUpgrade(
            base,
            packages,
            base_version="1.0.10",
            target_version="99.0.1",
            base_commit="5b47ebb",
            archive_sha256=DIGEST,
            schema_rollback=True,
        )
        published.validate()
        scenario(root / "real-migration-rollback", True, published)
    print(
        "PASS: immutable public 1.0.10 -> final 0006 catalog migration -> forced failure -> original schema/data/health restored, delta-only"
    )


if __name__ == "__main__":
    main()

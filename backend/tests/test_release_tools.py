"""Exercise the actual release-tool CLIs, not only their underlying engine."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import bsdiff4

from app.services.update_engine import build_manifest, manifest_to_json, sha256_bytes

ROOT = Path(__file__).resolve().parents[2]


def test_bspatch_cli_without_pythonpath(tmp_path: Path) -> None:
    old = b"old payload\n" * 1000
    new = b"new payload\n" * 1000
    (tmp_path / "old").write_bytes(old)
    (tmp_path / "patch").write_bytes(bsdiff4.diff(old, new))
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bspatch.py"), str(tmp_path / "old"),
         str(tmp_path / "new"), str(tmp_path / "patch")],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "new").read_bytes() == new


def test_delta_ships_hash_verified_standalone_helper(tmp_path: Path) -> None:
    base, target, out = (tmp_path / n for n in ("base", "target", "out"))
    base.mkdir()
    target.mkdir()
    (base / "version.json").write_text('{"version":"1.0.5"}')
    (target / "version.json").write_text('{"version":"1.0.6"}')
    (target / "scripts").mkdir()
    db_tool = (ROOT / "scripts/update_database.py").read_bytes()
    (target / "scripts/update_database.py").write_bytes(db_tool)
    helper = b"MZ-fixture-helper"
    (target / "vira-updater.exe").write_bytes(helper)
    (base / "install_manifest.json").write_text(json.dumps(manifest_to_json(build_manifest(base))))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/gen_delta.py"),
         "--base-manifest", str(base / "install_manifest.json"),
         "--base-dir", str(base), "--target-dir", str(target),
         "--base-version", "1.0.5", "--target-version", "1.0.6", "--out", str(out)],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(out / "VIRA-v1.0.6-delta-from-v1.0.5.zip") as archive:
        assert archive.read("update_database.py") == db_tool
        assert archive.read("vira-updater.exe") == helper
        assert archive.read("files/vira-updater.exe") == helper
        doc = json.loads(archive.read("update.json"))
        assert doc["hashes"]["vira-updater.exe"] == sha256_bytes(helper)
        assert doc["hashes"]["update_database.py"] == sha256_bytes(db_tool)

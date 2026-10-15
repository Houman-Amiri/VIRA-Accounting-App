"""scripts/bspatch.py — the updater's pure-Python BSDIFF40 applier (v1.0.3 fix).

Round-trips real bsdiff4 patches (the exact artifacts gen_delta produces for
files > 256 KB) through the CLI the installed updater invokes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import bsdiff4

REPO_ROOT = Path(__file__).resolve().parents[2]
BSPATCH = REPO_ROOT / "scripts" / "bspatch.py"


def run_bspatch(old: Path, new: Path, patch: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(BSPATCH), str(old), str(new), str(patch)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_bspatch_round_trip(tmp_path: Path) -> None:
    old = bytes(range(256)) * 2048  # 512 KB
    new = old[100:] + b"VIRA-EXTRA" + old[:5000]
    patch = bsdiff4.diff(old, new)

    old_f, new_f, patch_f = tmp_path / "old.bin", tmp_path / "out.bin", tmp_path / "p.bsdiff"
    old_f.write_bytes(old)
    patch_f.write_bytes(patch)

    proc = run_bspatch(old_f, new_f, patch_f)
    assert proc.returncode == 0, proc.stderr
    assert new_f.read_bytes() == new


def test_bspatch_from_empty_and_to_empty(tmp_path: Path) -> None:
    for old, new in ((b"", b"x" * 10_000), (b"y" * 10_000, b""), (b"", b"")):
        old_f, new_f, patch_f = tmp_path / "o", tmp_path / "n", tmp_path / "p"
        old_f.write_bytes(old)
        patch_f.write_bytes(bsdiff4.diff(old, new))
        proc = run_bspatch(old_f, new_f, patch_f)
        assert proc.returncode == 0, proc.stderr
        assert new_f.read_bytes() == new


def test_bspatch_rejects_garbage(tmp_path: Path) -> None:
    old_f, new_f, patch_f = tmp_path / "o", tmp_path / "n", tmp_path / "p"
    old_f.write_bytes(b"old")
    patch_f.write_bytes(b"not-a-bsdiff40-patch")
    proc = run_bspatch(old_f, new_f, patch_f)
    assert proc.returncode == 1
    assert "bspatch failed" in proc.stderr

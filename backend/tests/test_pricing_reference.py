"""Keep the frontend pricing oracle tied to the original XLSX, not hand-written prices."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_pricing_fixture_matches_workbook_and_cached_values() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/extract_pricing_reference.py"), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

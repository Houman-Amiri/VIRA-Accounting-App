"""bspatch — apply a BSDIFF40 patch (delta updates, Phase 8 §6).

Pure-Python wrapper around ``app.services.update_engine.apply_bsdiff`` so the
updater works without a native ``tools\\bspatch.exe``. Uses the bundled CPython
when present ({app}\\python\\python.exe), any system Python otherwise.

Usage:  python bspatch.py <old-file> <new-file> <patch-file>
"""

from __future__ import annotations

import sys
from pathlib import Path

# works from the repo checkout (<root>/backend/app) and the installed payload
# (<root>/app) — whichever resolves first wins
_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root / "backend"))
sys.path.insert(0, str(_root))

from app.services.update_engine import apply_bsdiff  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    old_path, new_path, patch_path = map(Path, sys.argv[1:4])
    old = old_path.read_bytes()
    patch = patch_path.read_bytes()
    try:
        new = apply_bsdiff(patch, old)
    except Exception as exc:  # noqa: BLE001 - surfaced as a non-zero exit
        print(f"bspatch failed: {exc}", file=sys.stderr)
        return 1
    new_path.write_bytes(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

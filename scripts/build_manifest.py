"""Build ``install_manifest.json`` for a packaged app directory (Phase 8 §1).

Every installed file is recorded as ``{path, sha256, size}`` — the baseline the
delta generator diffs and the updater verifies against.

Usage:
    python scripts/build_manifest.py <package_dir> [-o install_manifest.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.update_engine import build_manifest, manifest_sha256, manifest_to_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build install_manifest.json")
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument(
        "--skip",
        action="append",
        default=["install_manifest.json", "rollback", "updates"],
        help="relative paths/names to exclude (repeatable)",
    )
    args = parser.parse_args()
    root: Path = args.package_dir
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    manifest = build_manifest(root, skip_names=set(args.skip))
    payload = manifest_to_json(manifest)
    payload["files_manifest_sha256"] = manifest_sha256(manifest)
    out = args.output or (root / "install_manifest.json")
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[build_manifest] {len(manifest)} files -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

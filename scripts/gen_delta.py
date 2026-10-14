"""Generate a delta update package (Phase 8 §5).

Diffs the base installation manifest against the new build and produces
``VIRA-v<target>-delta-from-v<base>.zip`` containing:

- ``update.json``    ordered file operations (add / replace / patch / delete)
- ``files/``         new & changed small files, stored as-is
- ``patches/``       bsdiff patches for changed files above the threshold
- ``delete.json``    files removed in the target version
- every member's SHA-256 is listed in ``update.json``'s companion ``hashes``

Usage:
    python scripts/gen_delta.py --base-manifest old/install_manifest.json \
        --base-dir old_install --target-dir new_build \
        --base-version 1.4.0 --target-version 1.5.0 --out dist-release/
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import bsdiff4  # noqa: E402

from app.services.update_engine import (  # noqa: E402
    OpKind,
    build_manifest,
    manifest_from_json,
    plan_delta,
    sha256_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a delta update package")
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True, help="base install files (for patches)")
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--base-version", required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--patch-threshold", type=int, default=256 * 1024)
    args = parser.parse_args()

    base = manifest_from_json(json.loads(args.base_manifest.read_text(encoding="utf-8")))
    target = build_manifest(args.target_dir, skip_names={"install_manifest.json"})
    plan, members = plan_delta(
        args.base_version,
        args.target_version,
        base,
        target,
        patch_threshold=args.patch_threshold,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    name = f"VIRA-v{args.target_version}-delta-from-v{args.base_version}.zip"
    zip_path = args.out / name
    hashes: dict[str, str] = {}
    deletes = [o.path for o in plan.operations if o.op is OpKind.DELETE]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for member, (kind, rel) in sorted(members.items()):
            if kind is OpKind.PATCH:
                old = (args.base_dir / rel).read_bytes()
                new = (args.target_dir / rel).read_bytes()
                data = bsdiff4.diff(old, new)
            else:
                data = (args.target_dir / rel).read_bytes()
            zf.writestr(member, data)
            hashes[member] = sha256_bytes(data)
        zf.writestr("delete.json", json.dumps({"deleted": deletes}, indent=2))
        update_doc = plan.to_json()
        update_doc["hashes"] = hashes
        update_doc["delete_sha256"] = sha256_bytes(
            json.dumps({"deleted": deletes}, separators=(",", ":")).encode("utf-8")
        )
        zf.writestr("update.json", json.dumps(update_doc, indent=2, ensure_ascii=False))

    size = zip_path.stat().st_size
    print(f"[gen_delta] {zip_path.name}: {size} bytes, {len(members)} members, {len(deletes)} deletes")
    print(f"[gen_delta] sha256={sha256_bytes(zip_path.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

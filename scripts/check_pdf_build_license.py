"""Verify the owner's LIMITED MIT grant for native PDF build files.

No native build, binary staging, application license or distribution approval.
The exact scope is listed externally so archived build files need not be changed.
This checker is itself one of the explicitly MIT-licensed build-tooling files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PATH = "docs/dependencies/pdf-build-script-license-scope.json"
LICENSE_PATH = "LICENSES/VIRA-PDF-BUILD-MIT.txt"
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
SOURCE_COMMIT = "2ec79b82ccebc89d754dbe25c10aeef4c31d8738"
SOURCE_SHA256 = "259532d2cd8c5d3b176402acdcfb9daadb2cb897d5710010cc198eeabe5401de"
ARCHIVED_MEMBERS = {
    ".github/workflows/pdf-source-proof.yml": "vira-build/.github/workflows/pdf-source-proof.yml",
    "scripts/source_pdf_build.ps1": "vira-build/scripts/source_pdf_build.ps1",
    "scripts/source_pdf_inventory.py": "vira-build/scripts/source_pdf_inventory.py",
    "native/pdf-source/README.md": "vira-recipe/README.md",
    "native/pdf-source/vcpkg.json": "vira-recipe/vcpkg.json",
    "native/pdf-source/triplets/x64-vira-pdf.cmake": "vira-recipe/triplets/x64-vira-pdf.cmake",
    "native/pdf-source/triplets/x64-vira-pdf-host.cmake": "vira-recipe/triplets/x64-vira-pdf-host.cmake",
}
ALLOWED_FILES = frozenset({
    ".github/workflows/pdf-source-proof.yml",
    "native/pdf-source/README.md",
    "native/pdf-source/triplets/x64-vira-pdf-host.cmake",
    "native/pdf-source/triplets/x64-vira-pdf.cmake",
    "native/pdf-source/vcpkg.json",
    "scripts/source_pdf_build.ps1",
    "scripts/source_pdf_inventory.py",
    "scripts/pdf_runtime_inventory.py",
    "scripts/check_pdf_build_license.py",
    "scripts/rebuild_pdf_native.ps1",
    "scripts/audit_pdf_native_rebuild.py",
})


def canonical(data: bytes) -> bytes:
    """Normalize checkout CRLF only; preserve every other UTF-8 source character."""
    text = data.decode("utf-8")
    return text.replace("\r\n", "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


def read_scoped(root: Path, name: str) -> bytes:
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"External or symlinked licensed file: {name}")
    return path.read_bytes()


def verify(root: Path, scope: dict) -> dict:
    if (scope["schema"] != 1 or scope["license_id"] != "MIT" or scope["license_file"] != LICENSE_PATH
            or scope["hash_format"] != "UTF8_CRLF_TO_LF_SHA256_V1"):
        raise ValueError("Unexpected license or hash format")
    if set(scope["files"]) != ALLOWED_FILES:
        raise ValueError("License scope must be the exact approved native-build allowlist")
    consent = scope["owner_authorization"]
    if (consent["status"] != "CONFIRMED_SCOPED_MIT" or consent["date"] != "2026-10-18"
            or consent["application_license_changed"] is not False
            or consent["release_authorized"] is not False):
        raise ValueError("Owner consent is scoped; not an application license or release approval")
    if scope["runtime_distribution_status"] != BLOCKED:
        raise ValueError("Native runtime must remain blocked")
    if scope["source_archive_sha256"] != SOURCE_SHA256:
        raise ValueError("Source archive reference changed")
    for name, record in scope["files"].items():
        if record["corresponding_source_member"] != ARCHIVED_MEMBERS.get(name):
            raise ValueError(f"Archived license scope binding changed: {name}")
        if name in ARCHIVED_MEMBERS and record.get("source_build_reference_commit") != SOURCE_COMMIT:
            raise ValueError(f"Archived source commit changed: {name}")
    license_bytes = read_scoped(root, LICENSE_PATH)
    if digest(license_bytes) != scope["license_sha256_lf"]:
        raise ValueError("MIT license bytes changed")
    text = canonical(license_bytes).decode("utf-8")
    for clause in ("MIT License", "Copyright (c) 2026 VIRA contributors",
                   "Permission is hereby granted, free of charge", "copies or substantial portions",
                   'THE SOFTWARE IS PROVIDED "AS IS"', "AUTHORS OR COPYRIGHT HOLDERS"):
        if clause not in text:
            raise ValueError("Incomplete MIT license")
    for name, record in scope["files"].items():
        if digest(read_scoped(root, name)) != record["sha256_lf"]:
            raise ValueError(f"Licensed reference content changed; review/update scope explicitly: {name}")
    return {
        "license_id": "MIT", "licensed_file_count": len(ALLOWED_FILES),
        "permission_status": "OWNER_CONFIRMED_FOR_LISTED_BUILD_FILES_ONLY",
        "application_license_changed": False, "release_authorized": False,
        "runtime_distribution_status": BLOCKED,
        "standalone_recipe_completeness": "NOT_PROVEN_BY_LICENSE_GRANT",
    }


def write_sidecar(root: Path, scope: dict, destination: Path) -> None:
    """Copy only verified licensed files and their grant; no app or native DLLs."""
    verify(root, scope)
    destination.mkdir(parents=True, exist_ok=False)
    for name in [*sorted(ALLOWED_FILES), LICENSE_PATH, SCOPE_PATH]:
        data = read_scoped(root, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / "README.txt").write_text(
        "VIRA native PDF build files — limited MIT grant\n"
        "MIT applies ONLY to the reference files listed in the included scope JSON.\n"
        "Keep the complete license and copyright with copies/substantial portions.\n"
        "This sidecar supplies the licensed helper pdf_runtime_inventory.py that\n"
        "was missing from the original archive's wrapper appendix.\n"
        "It is NOT the whole application, a full standalone workflow, an offline\n"
        "compiler SDK or permission to redistribute third-party/CRT binaries.\n"
        "The OLD workflow still references app/staging files outside this grant.\n"
        "Native-only entry point (Windows x64, PowerShell 7, Git, MSVC/SDK):\n"
        "  pwsh -File scripts/rebuild_pdf_native.ps1 -WorkDir C:/new-native-build\n"
        "Use a NEW absolute directory; native build tools may be downloaded.\n"
        "No Node, uv, application Python environment or app checkout is required.\n"
        "Original corresponding-source.zip remains unchanged; deliver its upstream\n"
        "notices and this grant together at an explicitly authorized future release.\n",
        encoding="utf-8", newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Optional review JSON, not a distribution approval")
    parser.add_argument("--sidecar", type=Path, help="New directory for scoped licensed sources; never overwrite")
    args = parser.parse_args()
    scope = json.loads((ROOT / SCOPE_PATH).read_text(encoding="utf-8"))
    result = verify(ROOT, scope)
    if args.sidecar:
        write_sidecar(ROOT, scope, args.sidecar)
    rendered = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")


if __name__ == "__main__":
    main()

"""MIT native-build tooling derivative: assemble/check a review-only source kit.

SPDX-License-Identifier: MIT
Copyright (c) 2026 VIRA contributors

Standard library only. Never publish, install native binaries or grant clearance.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import posixpath
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
SOURCE_SHA = "259532d2cd8c5d3b176402acdcfb9daadb2cb897d5710010cc198eeabe5401de"
DOCS = (
    "pdf-runtime-win64-source-inventory.json", "pdf-runtime-license-policy.json",
    "pdf-runtime-license-review.json", "pdf-runtime-license-materials.json",
    "pdf-runtime-THIRD-PARTY-NOTICES.txt", "pdf-native-rebuild-guide.md",
    "pdf-crt-official-reference-review.json",
)
README = """VIRA native PDF SOURCE KIT — PRIVATE REVIEW ONLY

This is not an installer, offline compiler SDK, publication or legal approval.
No application checkout, app Python environment, Node or uv is needed to compile.
Windows x64, PowerShell 7, Git, appropriately licensed MSVC/SDK and network access
are required. vcpkg can download its own build tools, including Python/Meson.

1. Verify the external publisher's SHA256 for this kit/manifest through a trusted
   channel. A self-contained manifest is NOT authentication or a digital signature.
2. Check with trusted Python 3.11+ (standard library only, no app dependencies):
   python -I -S licensed-build-files/scripts/pdf_source_kit.py --verify KIT_DIRECTORY
   Add --expected-manifest-sha256 HASH from the independent receipt when available.
3. To extract the ORIGINAL source ZIP with relative symlinks preserved:
   python -I -S licensed-build-files/scripts/pdf_source_kit.py --verify KIT_DIRECTORY --extract-sources NEW_DIRECTORY
   Windows needs permission to create symlinks (e.g. Developer Mode). Failure is
   explicit; links are NEVER silently turned into regular files. Existing output
   directories are refused. Do not use a generic ZIP extractall for inner sources.
4. cd licensed-build-files
   pwsh -NoProfile -File scripts/rebuild_pdf_native.ps1 -WorkDir C:/new-native-build
   See evidence/pdf-native-rebuild-guide.md for plan, overlays and optional audit.
   This command downloads verified upstream inputs at the pinned vcpkg baseline;
   it does not automatically consume extracted preferred-source trees. Modified
   local sources need reviewed overlay ports; offline/local-source replay is NOT
   established by this kit. Historical app-dependent wrappers are not the entry.

MIT covers ONLY the explicit build-tool scope and derivatives. Keep the full MIT
notice with those files; third-party sources/notices/CRT have independent terms.
Evidence documents are compliance/build instructions, not an app-wide license.
The accounting app and compiler/SDK/native binary payload are NOT supplied here.
The original source ZIP and its seven historical grant bindings are unchanged.

All six native distribution gates remain tracked. Recipient delivery/public URLs,
LGPL replacement/EULA, CRT entitlement/static components, production bootstrap and
native updates still require review/testing. Actions retention is not durable
recipient source delivery. BLOCKED is project release readiness, not an extra MIT
restriction. No release/tag/version or user data is changed by these commands.
"""


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(name: str) -> str:
    p = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or "\0" in name or p.is_absolute()
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ValueError(f"Unsafe archive/manifest path: {name!r}")
    return name


def source_entries(bundle: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], dict[str, str]]:
    entries = bundle.infolist()
    if len(entries) > 100000 or sum(i.file_size for i in entries) > 4 * 1024**3:
        raise ValueError("Source archive exceeds inspection bounds")
    names: set[str] = set()
    links = {}
    for entry in entries:
        name = relative(entry.filename)
        if name.casefold() in names:
            raise ValueError("Duplicate/case-colliding source archive entry")
        names.add(name.casefold())
        for part in PurePosixPath(name).parts:
            reserved = part.split(".")[0].upper()
            if part.endswith((".", " ")) or reserved in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
                raise ValueError("Nonportable Windows source path")
        mode = entry.external_attr >> 16
        if entry.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFLNK)):
            raise ValueError("Only source files and relative symlinks are supported")
        if entry.file_size > 256 * 1024**2:
            raise ValueError("Source entry exceeds inspection bounds")
        if stat.S_ISLNK(mode):
            target = bundle.read(entry).decode("utf-8")
            if not target or "\\" in target or ":" in target or "\0" in target or target.startswith("/"):
                raise ValueError("Unsafe symlink target")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            parts = PurePosixPath(name).parts
            if len(parts) < 3 or parts[0] != "sources" or not resolved.startswith(f"sources/{parts[1]}/"):
                raise ValueError("Symlink escapes its source package")
            links[name] = target
    actual = {i.filename for i in entries}
    regular_files = actual - set(links)
    for name in actual:
        if any(str(parent) in regular_files for parent in PurePosixPath(name).parents):
            raise ValueError("File/directory ancestor collision")
        if any(str(parent) in links for parent in PurePosixPath(name).parents):
            raise ValueError("Archive writes through a symlink ancestor")
    for name, target in links.items():
        seen = {name}
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
        while resolved in links:
            if resolved in seen:
                raise ValueError("Cyclic source symlink")
            seen.add(resolved)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(resolved), links[resolved]))
        if any(str(parent) in links for parent in PurePosixPath(resolved).parents):
            raise ValueError("Symlink target traverses a symlink ancestor")
        if resolved not in actual and not any(n.startswith(resolved + "/") for n in actual):
            raise ValueError("Dangling source symlink")
    return entries, links


def verify_sources(archive: Path, inventory: dict) -> dict:
    pin = inventory["source_archive"]
    if (pin["sha256"] != SOURCE_SHA or sha_file(archive) != SOURCE_SHA
            or archive.stat().st_size != pin["size"] or inventory["distribution_status"] != BLOCKED
            or inventory["source_tree_hash_format"] != "UTF8_POSIX_PATH_NUL_KIND_NUL_SHA256_LF_CASE_SENSITIVE_V1"):
        raise ValueError("Wrong pinned corresponding-source archive or provenance")
    counts = {"packages": 0, "source_entries": 0, "source_symlinks": 0}
    with zipfile.ZipFile(archive) as bundle:
        entries, links = source_entries(bundle)
        captured = {PurePosixPath(i.filename).parts[1] for i in entries if i.filename.startswith("sources/")}
        expected = {n for n, p in inventory["source_packages"].items() if p["patched_source_files"]}
        if captured != expected:
            raise ValueError("Captured source package set differs")
        for name, package in inventory["source_packages"].items():
            prefix = f"sources/{name}/"
            files = sorted(i.filename for i in entries if i.filename.startswith(prefix))
            digest = hashlib.sha256()
            for filename in files:
                data = bundle.read(filename)
                kind = b"symlink" if filename in links else b"file"
                digest.update(filename[len(prefix):].encode() + b"\0" + kind + b"\0" + hashlib.sha256(data).hexdigest().encode() + b"\n")
            expected_links = {n[len(prefix):]: t for n, t in links.items() if n.startswith(prefix)}
            if (len(files) != package["patched_source_files"]
                    or digest.hexdigest() != package["patched_source_tree_sha256"]
                    or expected_links != package["patched_source_symlinks"]):
                raise ValueError(f"Preferred-source tree mismatch: {name}")
            counts["packages"] += 1
            counts["source_entries"] += len(files)
            counts["source_symlinks"] += len(expected_links)
    return counts


def checker(root: Path):
    spec = importlib.util.spec_from_file_location("kit_scope_checker", root / "scripts/check_pdf_build_license.py")
    if spec is None or spec.loader is None:
        raise ValueError("Scope checker unavailable")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def build(root: Path, archive: Path, destination: Path) -> dict:
    scope = json.loads((root / "docs/dependencies/pdf-build-script-license-scope.json").read_text(encoding="utf-8"))
    tool = checker(root)
    tool.verify(root, scope)
    inventory = json.loads((root / "docs/dependencies/pdf-runtime-win64-source-inventory.json").read_text(encoding="utf-8"))
    verify_sources(archive, inventory)
    destination.mkdir(parents=True, exist_ok=False)
    tool.write_sidecar(root, scope, destination / "licensed-build-files")
    shutil.copyfile(archive, destination / "corresponding-source.zip")
    (destination / "evidence").mkdir()
    for name in DOCS:
        source = root / "docs/dependencies" / name
        if source.is_symlink():
            raise ValueError("Symlinked kit evidence")
        shutil.copyfile(source, destination / "evidence" / name)
    (destination / "README.txt").write_text(README, encoding="utf-8", newline="\n")
    files = {p.relative_to(destination).as_posix(): {"sha256": sha_file(p), "size": p.stat().st_size}
             for p in sorted(destination.rglob("*")) if p.is_file()}
    manifest = {"schema": 1, "status": "PRIVATE_REVIEW_KIT_NOT_RECIPIENT_DELIVERY",
                "distribution_status": BLOCKED, "files": files}
    (destination / "kit-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return verify(destination)


def verify_evidence(kit: Path, inventory: dict, licensed_count: int) -> None:
    evidence = kit / "evidence"
    policy = json.loads((evidence / "pdf-runtime-license-policy.json").read_text(encoding="utf-8"))
    review = json.loads((evidence / "pdf-runtime-license-review.json").read_text(encoding="utf-8"))
    materials = json.loads((evidence / "pdf-runtime-license-materials.json").read_text(encoding="utf-8"))
    official = json.loads((evidence / "pdf-crt-official-reference-review.json").read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    gates = {"COMPLETE_COMPONENT_LEGAL_REVIEW", "COMPILER_CRT_TERMS", "BUILD_SCRIPT_PERMISSIONS_AND_COMPLETENESS",
             "RECIPIENT_SOURCE_DELIVERY", "LGPL_SHARED_LIBRARY_REPLACEMENT", "PRODUCTION_BOOTSTRAP_UPDATES_AND_ACCEPTANCE"}
    if (any(x["distribution_status"] != BLOCKED for x in (policy, review, official))
            or any(x["source_archive"] != inventory["source_archive"] for x in (policy, review, materials))
            or policy["inventory_fingerprint_sha256"] != fingerprint
            or policy["open_gates"] != review["open_gates"]
            or next(g for g in policy["open_gates"] if g["id"] == "BUILD_SCRIPT_PERMISSIONS_AND_COMPLETENESS")["progress"]["licensed_files"] != licensed_count
            or {g["id"] for g in policy["open_gates"]} != gates
            or review["notices_sha256"] != sha_file(evidence / "pdf-runtime-THIRD-PARTY-NOTICES.txt")):
        raise ValueError("Inconsistent source/notices/policy evidence or missing distribution gates")
    with zipfile.ZipFile(kit / "corresponding-source.zip") as bundle:
        for name, item in materials["files"].items():
            data = bundle.read(relative(item["archive_path"]))
            if (hashlib.sha256(data).hexdigest() != item["sha256"] or data.decode("utf-8") != item["text"]
                    or review["supplement_sha256"][name] != item["sha256"]):
                raise ValueError("Supplement does not match original source archive")


def verify(kit: Path, expected_manifest_sha256: str | None = None) -> dict:
    manifest_path = kit / "kit-manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Symlinked kit manifest")
    manifest_sha = sha_file(manifest_path)
    if expected_manifest_sha256 is not None and manifest_sha != expected_manifest_sha256:
        raise ValueError("External manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest["schema"] != 1 or manifest["distribution_status"] != BLOCKED
            or manifest["status"] != "PRIVATE_REVIEW_KIT_NOT_RECIPIENT_DELIVERY"):
        raise ValueError("Kit is not a blocked review candidate")
    files = manifest["files"]
    entries = list(kit.rglob("*"))
    root = kit.resolve()
    if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in entries):
        raise ValueError("Symlink or external/junction path in kit envelope")
    if any(not p.is_file() and not p.is_dir() for p in entries):
        raise ValueError("Special file in kit envelope")
    actual = {p.relative_to(kit).as_posix() for p in entries if p.is_file()}
    if actual != set(files) | {"kit-manifest.json"}:
        raise ValueError("Kit has missing/unmanifested files")
    for name, record in files.items():
        p = kit / relative(name)
        if p.stat().st_size != record["size"] or sha_file(p) != record["sha256"]:
            raise ValueError(f"Kit file hash/size mismatch: {name}")
    licensed = kit / "licensed-build-files"
    # Never execute code from the directory being inspected. Use only the
    # verifier's own adjacent trusted checker (recipient must authenticate it).
    tool = checker(ROOT)
    scope = json.loads((licensed / tool.SCOPE_PATH).read_text(encoding="utf-8"))
    grant = tool.verify(licensed, scope)
    allowed = {"corresponding-source.zip", "README.txt", *(f"evidence/{n}" for n in DOCS),
               *(f"licensed-build-files/{n}" for n in tool.ALLOWED_FILES),
               f"licensed-build-files/{tool.LICENSE_PATH}", f"licensed-build-files/{tool.SCOPE_PATH}",
               "licensed-build-files/README.txt"}
    if set(files) != allowed:
        raise ValueError("Kit envelope scope changed; app/binary extras are forbidden")
    inventory = json.loads((kit / "evidence/pdf-runtime-win64-source-inventory.json").read_text(encoding="utf-8"))
    sources = verify_sources(kit / "corresponding-source.zip", inventory)
    verify_evidence(kit, inventory, grant["licensed_file_count"])
    return {"schema": 1, "distribution_status": BLOCKED, "kit_manifest_sha256": manifest_sha,
            "external_manifest_hash_checked": expected_manifest_sha256 is not None,
            "authentication": "REQUIRES_TRUSTED_EXTERNAL_DIGEST_AND_VERIFIER",
            "kit_files": len(files), "licensed_files": grant["licensed_file_count"], "verified_sources": sources,
            "source_archive_sha256": SOURCE_SHA, "recipient_source_delivery": False}


def extract_sources(kit: Path, destination: Path, expected_manifest_sha256: str | None = None) -> None:
    verify(kit, expected_manifest_sha256)
    with zipfile.ZipFile(kit / "corresponding-source.zip") as bundle:
        entries, links = source_entries(bundle)
        destination.mkdir(parents=True, exist_ok=False)
        for entry in entries:
            if entry.filename in links:
                continue
            target = destination / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            # Preserve executable source scripts; never restore setuid/setgid bits.
            target.chmod((entry.external_attr >> 16) & 0o777 or 0o644)
        for name, target in sorted(links.items()):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            resolved = destination / posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            os.symlink(target, path, target_is_directory=resolved.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--extract-sources", type=Path)
    args = parser.parse_args()
    if args.verify:
        if args.archive or args.out:
            parser.error("verify and build modes are separate")
        result = verify(args.verify, args.expected_manifest_sha256)
        if args.extract_sources:
            extract_sources(args.verify, args.extract_sources, args.expected_manifest_sha256)
    else:
        if not args.archive or not args.out or args.extract_sources or args.expected_manifest_sha256:
            parser.error("build requires --archive and --out; extraction/hash are verify-only")
        result = build(ROOT, args.archive, args.out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

"""MIT native-build tooling derivative: assemble/check a review-only source kit.

SPDX-License-Identifier: MIT
Copyright (c) 2026 VIRA contributors

Standard library only. Never publish, install native binaries or grant clearance.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import posixpath
import shutil
import stat
import sys
import time
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
   This default command downloads upstream target sources; it is NOT local replay.
5. For LOCAL preferred inputs, first authenticate/extract as above, then run:
   python -I -S licensed-build-files/scripts/prepare_pdf_local_sources.py --kit KIT_DIRECTORY --expected-manifest-sha256 HASH --sources NEW_DIRECTORY --out NEW_OVERLAY
   Use NEW absolute paths OUTSIDE the input kit/preferred tree for all outputs.
   From licensed-build-files run the same native driver with -OverlayPorts NEW_OVERLAY
   and a NEW absolute WorkDir. After compilation, check external inputs with:
   python -I -S scripts/prepare_pdf_local_sources.py --check-inputs NEW_OVERLAY/local-source-preparation.json
   See evidence/pdf-native-rebuild-guide.md for explicit --allow-modified,
   target-only bounded adapters, preserved links and PCRE2/SLJIT/APNG limits.
   Host/build-tool downloads still need network; this is NOT an offline SDK.
   Generated recipes alone are not build proof. Modified inputs need a distinct
   source reference and eventual corresponding-source archive, not a false claim
   that the immutable original ZIP corresponds unchanged to the new DLLs.
   Historical app-dependent wrappers are not the independent entry point.

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
    if destination.resolve().is_relative_to(kit.resolve()):
        raise ValueError("Extraction output must be outside the source kit")
    verify(kit, expected_manifest_sha256)
    extract_archive(kit / "corresponding-source.zip", destination)


def extract_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        entries, links = source_entries(bundle)
        destination.mkdir(parents=True, exist_ok=False)
        for entry in entries:
            if entry.filename in links:
                continue
            target = destination / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            # Autotools uses relative mtimes to decide whether to regenerate
            # configure/Makefile.in. Fresh extraction-order times can trigger an
            # unintended autoreconf with a different toolchain. ZIP stores local
            # wall time at two-second precision; restore those recorded fields.
            modified = time.mktime((*entry.date_time, 0, 0, -1))
            os.utime(target, (modified, modified))
            # Preserve executable source scripts; never restore setuid/setgid bits.
            target.chmod((entry.external_attr >> 16) & 0o777 or 0o644)
        for name, target in sorted(links.items()):
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            resolved = destination / posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            # Windows reparse-point targets need native separators. A relative
            # POSIX target containing '/' may exist as a link yet not resolve.
            # Captured/digested targets remain canonical POSIX strings.
            os.symlink(target.replace("/", os.sep), path, target_is_directory=resolved.is_dir())


MODIFIED_STATUS = "PRIVATE_MODIFIED_SOURCE_REVIEW_NOT_RECIPIENT_DELIVERY"
MODIFIED_MANIFEST = "modified-kit-manifest.json"
MODIFIED_EXTRAS = {"modified-corresponding-source.zip", "native-build-witness.json",
                   "modification-record.json", "VIRA-MODIFICATIONS.txt", "README.txt"}


def modified_record(base: Path, witness: Path, expected_witness_sha256: str, change_date: str) -> tuple[dict, dict]:
    """Authenticate the recorded compiled bytes, not arbitrary edits or version text."""
    if datetime.date.fromisoformat(change_date).isoformat() != change_date:
        raise ValueError("Canonical ISO modification date required")
    if sha_file(witness) != expected_witness_sha256:
        raise ValueError("External native witness hash mismatch")
    proof = json.loads(witness.read_text(encoding="utf-8"))
    if (proof["distribution_status"] != BLOCKED or proof["native_compilation"] != "SUCCESS"
            or proof["local_preferred_source_replay"] != "SUCCESS"
            or proof["private_local_source_payload_pdf"] != "SUCCESS"
            or proof["changed_packages"] != ["pango"] or proof["dll_count"] != 21
            or len(proof["dlls"]) != 21
            or proof["actual_pango_version_string"] != "1.58.0-vira-local-source"
            or proof["input_source_trees_unchanged_during_compilation"] is not True
            or proof["original_archive_modified"] is not False
            or proof["kit_receipt"]["source_archive_sha256"] != SOURCE_SHA):
        raise ValueError("Successful modified-source native/app witness required")
    edit = proof["explicit_edit"]
    member = "sources/pango/" + relative(edit["file"])
    if not member.endswith("/pango/pango-utils.c") or edit["package"] != "pango":
        raise ValueError("Only the witnessed Pango version edit is supported")
    data = edit["modified_source_file"].encode("utf-8")
    if hashlib.sha256(data).hexdigest() != edit["after_sha256"]:
        raise ValueError("Witness modified source bytes differ")
    with zipfile.ZipFile(base / "corresponding-source.zip") as archive:
        original = archive.read(member)
    before, after = b"return PANGO_VERSION_STRING;", b'return PANGO_VERSION_STRING "-vira-local-source";'
    if (hashlib.sha256(original).hexdigest() != edit["before_sha256"]
            or original.count(before) != 1 or original.replace(before, after) != data):
        raise ValueError("Source modification differs from the actual controlled edit")
    inventory = json.loads((base / "evidence/pdf-runtime-win64-source-inventory.json").read_text(encoding="utf-8"))
    trees = proof["preferred_source_trees"]
    if len(trees) != 20 or set(trees) != set(inventory["source_packages"]):
        raise ValueError("Twenty compiled source trees required")
    for name, package in inventory["source_packages"].items():
        if (trees[name]["source_entries"] != package["patched_source_files"]
                or (name != "pango" and trees[name]["tree_sha256"] != package["patched_source_tree_sha256"])):
            raise ValueError("Unrelated source tree differs from native build")
    record = {"schema": 1, "distribution_status": BLOCKED, "original_archive_sha256": SOURCE_SHA,
              "native_build_witness_sha256": expected_witness_sha256, "modification_date": change_date,
              "modified_member": member, "before_sha256": edit["before_sha256"], "after_sha256": edit["after_sha256"],
              "expected_pango_version": "1.58.0-vira-local-source", "compiled_source_trees": trees,
              "new_modified_source_archive_prepared": True, "recipient_source_delivery": False,
              "modified_build_is_distribution_candidate": False,
              "inline_change_date_notice_present_in_compiled_source": False,
              "legal_notice_completeness_approved": False}
    return record, proof


INLINE_VARIANT = "INLINE_NOTICE_PENDING_FRESH_BUILD_V1"


def noticed_file(change_date: str, previous_file: bytes) -> bytes:
    """Prominent in-file notice; retain all original headers and actual version edit."""
    if datetime.date.fromisoformat(change_date).isoformat() != change_date:
        raise ValueError("Canonical ISO modification date required")
    return (f"/* VIRA modification notice - {change_date}\n"
            " * Modified by VIRA contributors for the private native-source replay test.\n"
            " * pango_version_string() appends the suffix -vira-local-source.\n"
            " * This dated notice is part of the modified source file itself.\n"
            " * Original upstream copyright and license terms below are retained.\n"
            " */\n").encode("ascii") + previous_file


def noticed_record(base: Path, witness: Path, expected_witness_sha256: str, change_date: str) -> tuple[dict, dict]:
    record, proof = modified_record(base, witness, expected_witness_sha256, change_date)
    data = noticed_file(change_date, proof["explicit_edit"]["modified_source_file"].encode("utf-8"))
    record.update(archive_variant=INLINE_VARIANT, prior_modified_file_sha256=record["after_sha256"],
                  after_sha256=hashlib.sha256(data).hexdigest(),
                  inline_change_date_notice_present_in_archive_source=True,
                  prior_build_witness_applies_to_archive_sources=False,
                  compiled_source_trees_is_prior_witness_only=True,
                  archive_source_trees=copy.deepcopy(record["compiled_source_trees"]))
    # Compute the new Pango tree from the complete original source ZIP, not a
    # fabricated future build witness. Every other tree retains its prior hash.
    prefix = "sources/pango/"
    with zipfile.ZipFile(base / "corresponding-source.zip") as archive:
        entries, links = source_entries(archive)
        files = sorted(e.filename for e in entries if e.filename.startswith(prefix))
        digest = hashlib.sha256()
        for name in files:
            content = data if name == record["modified_member"] else archive.read(name)
            kind = b"symlink" if name in links else b"file"
            digest.update(name[len(prefix):].encode() + b"\0" + kind + b"\0"
                          + hashlib.sha256(content).hexdigest().encode() + b"\n")
    record["archive_source_trees"]["pango"] = {"source_entries": len(files), "tree_sha256": digest.hexdigest()}
    return record, proof



def modification_notice(record: dict) -> str:
    if record.get("archive_variant") == INLINE_VARIANT:
        return ("VIRA NOTICED PANGO SOURCE CANDIDATE - PRIVATE REVIEW ONLY\n"
                f"Modified file: {record['modified_member']}\n"
                f"Modification/inline-notice date: {record['modification_date']}\n"
                "Change: version suffix -vira-local-source, with a prominent dated in-file notice.\n"
                f"Original file SHA256: {record['before_sha256']}\n"
                f"Prior modified file SHA256: {record['prior_modified_file_sha256']}\n"
                f"New noticed file SHA256: {record['after_sha256']}\n"
                "Original upstream headers/licenses and all other archive members are retained.\n"
                "The retained PRIOR build witness does NOT prove these new noticed source bytes.\n"
                "A separate fresh build/PDF witness must bind this archive and all twenty trees.\n"
                "Presence of this notice is not full component/CRT/EULA legal sign-off or delivery.\n"
                + BLOCKED + "\n")
    return ("VIRA CONTROLLED PANGO MODIFICATION — PRIVATE SOURCE REVIEW\n"
            f"Modified file: {record['modified_member']}\n"
            f"Modification date (producer record): {record['modification_date']}\n"
            "Change: append -vira-local-source to pango_version_string().\n"
            f"Before SHA256: {record['before_sha256']}\nAfter SHA256: {record['after_sha256']}\n"
            "The complete modified file is supplied, not only a patch. Original upstream\n"
            "copyright/license headers and all captured upstream license files are retained.\n"
            "Compiled bytes have no new inline VIRA change/date notice. This external notice\n"
            "does NOT certify LGPL notice completeness or distribution compliance. Adding an\n"
            "inline notice later changes source bytes and requires a fresh build/reference.\n"
            "No CRT permission, public delivery, installed replacement or release approval.\n"
            + BLOCKED + "\n")


def verify_modified_archive(archive: Path, base: Path, record: dict, proof: dict) -> dict:
    """Check every original member and source tree, including modes, times and links."""
    source_data = proof["explicit_edit"]["modified_source_file"].encode("utf-8")
    if record.get("archive_variant") == INLINE_VARIANT:
        source_data = noticed_file(record["modification_date"], source_data)
    expected_trees = record.get("archive_source_trees", record["compiled_source_trees"])
    with zipfile.ZipFile(base / "corresponding-source.zip") as original, zipfile.ZipFile(archive) as changed:
        old_entries, old_links = source_entries(original)
        entries, links = source_entries(changed)
        old = {e.filename: e for e in old_entries}
        new = {e.filename: e for e in entries}
        if (set(new) != set(old) | {"VIRA-MODIFICATIONS.txt"} or links != old_links
                or changed.comment != original.comment):
            raise ValueError("Modified archive member/link coverage differs")
        if changed.read("VIRA-MODIFICATIONS.txt") != modification_notice(record).encode("utf-8"):
            raise ValueError("Prominent modification notice differs")
        for name, entry in old.items():
            other = new[name]
            if (entry.external_attr != other.external_attr or entry.date_time != other.date_time
                    or entry.create_system != other.create_system or entry.comment != other.comment
                    or entry.extra != other.extra or entry.internal_attr != other.internal_attr
                    or entry.compress_type != other.compress_type):
                raise ValueError(f"Archive mode/time metadata changed: {name}")
            actual = changed.read(name)
            expected = source_data if name == record["modified_member"] else original.read(name)
            if actual != expected:
                raise ValueError(f"Unwitnessed modified archive content: {name}")
        count = 0
        for name, expected in expected_trees.items():
            prefix = f"sources/{name}/"
            files = sorted(n for n in new if n.startswith(prefix))
            digest = hashlib.sha256()
            for member in files:
                kind = b"symlink" if member in links else b"file"
                digest.update(member[len(prefix):].encode() + b"\0" + kind + b"\0"
                              + hashlib.sha256(changed.read(member)).hexdigest().encode() + b"\n")
            if len(files) != expected["source_entries"] or digest.hexdigest() != expected["tree_sha256"]:
                raise ValueError(f"Modified archive differs from compiled source tree: {name}")
            count += len(files)
    return {"packages": len(record["compiled_source_trees"]), "source_entries": count,
            "source_symlinks": len(links), "all_nonmodified_members_unchanged": True,
            "source_modes_and_zip_local_times_retained": True}


def build_modified(base: Path, expected_base_sha256: str, witness: Path, expected_witness_sha256: str,
                   change_date: str, destination: Path, *, inline_notice: bool = False) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("Fresh modified review output required")
    if destination.resolve().is_relative_to(base.resolve()) or destination.resolve().is_relative_to(witness.parent.resolve()):
        raise ValueError("Modified output must be outside kit/witness inputs")
    receipt = verify(base, expected_base_sha256)
    make_record = noticed_record if inline_notice else modified_record
    record, proof = make_record(base, witness, expected_witness_sha256, change_date)
    source_data = proof["explicit_edit"]["modified_source_file"].encode("utf-8")
    if inline_notice:
        source_data = noticed_file(change_date, source_data)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(base, destination / "original-kit")
    shutil.copyfile(witness, destination / "native-build-witness.json")
    notice = modification_notice(record)
    (destination / "VIRA-MODIFICATIONS.txt").write_text(notice, encoding="utf-8", newline="\n")
    with zipfile.ZipFile(base / "corresponding-source.zip") as source, zipfile.ZipFile(
            destination / "modified-corresponding-source.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        output.comment = source.comment
        for entry in source.infolist():
            data = source_data if entry.filename == record["modified_member"] else source.read(entry)
            output.writestr(copy.copy(entry), data)
        info = zipfile.ZipInfo("VIRA-MODIFICATIONS.txt", (*datetime.date.fromisoformat(change_date).timetuple()[:3], 0, 0, 0))
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        output.writestr(info, notice.encode("utf-8"))
    record["modified_archive_sha256"] = sha_file(destination / "modified-corresponding-source.zip")
    record["modified_archive_size"] = (destination / "modified-corresponding-source.zip").stat().st_size
    record["original_kit_manifest_sha256"] = receipt["kit_manifest_sha256"]
    (destination / "modification-record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    (destination / "README.txt").write_text(
        "PRIVATE MODIFIED SOURCE REVIEW KIT — NOT PUBLIC RECIPIENT DELIVERY\n"
        "Authenticate this envelope manifest digest AND your verifier independently.\n"
        "Run trusted pdf_source_kit.py --verify-modified KIT --expected-manifest-sha256 HASH\n"
        "Add --extract-sources NEW_OUTSIDE_DIRECTORY for safe modified-source extraction.\n"
        "original-kit/ retains the immutable original ZIP, complete limited-MIT build\n"
        "sidecar and upstream notices/evidence. It is NOT the modified binary source ZIP.\n"
        "modified-corresponding-source.zip includes ALL original members, the exact\n"
        "witnessed modified Pango file, and a prominent external modification notice.\n"
        "All twenty preferred trees must equal those audited in the successful build.\n"
        "The older local-source adapter can use original-kit/ plus the extracted\n"
        "modified tree with --allow-modified; it intentionally keeps source_archive=null\n"
        "and does not itself bind this separately packaged review archive. No new build\n"
        "from THIS envelope is claimed. See VIRA-MODIFICATIONS.txt for inline-notice gap.\n"
        "Compiler/SDK/network prerequisites and all six legal/production gates remain.\n"
        "No app/QA harness license, DLLs, compiler, SDK or installed-user data supplied.\n",
        encoding="utf-8", newline="\n")
    if inline_notice:
        (destination / "README.txt").write_text(
            "PRIVATE NOTICED SOURCE CANDIDATE - REQUIRES FRESH BUILD/PDF ATTESTATION\n"
            "All original sources/recipes/licenses remain in original-kit/.\n"
            "modified-corresponding-source.zip contains full sources with the new dated\n"
            "notice INSIDE Pango's modified file. Old witness/source tree fields describe\n"
            "the prior build only, not this new source. archive_source_trees are the new\n"
            "candidate hashes; a fresh build must match all twenty before acceptance.\n"
            "Use an independently authenticated verifier/adjacent checker and external\n"
            "manifest digest with --verify-modified and --extract-sources NEW_OUTSIDE_DIR.\n"
            "Prepare with original-kit/ plus extracted sources and --allow-modified.\n"
            "No legal sign-off, public delivery, compiler/CRT right, installed replacement,\n"
            "production integration or release approval is inferred from packaging.\n",
            encoding="utf-8", newline="\n")
    files = {p.relative_to(destination).as_posix(): {"sha256": sha_file(p), "size": p.stat().st_size}
             for p in sorted(destination.rglob("*")) if p.is_file()}
    manifest = {"schema": 1, "status": MODIFIED_STATUS, "distribution_status": BLOCKED, "files": files}
    (destination / MODIFIED_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return verify_modified(destination, sha_file(destination / MODIFIED_MANIFEST))


def verify_modified(kit: Path, expected_manifest_sha256: str) -> dict:
    path = kit / MODIFIED_MANIFEST
    if path.is_symlink() or sha_file(path) != expected_manifest_sha256:
        raise ValueError("External modified manifest hash mismatch")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["schema"] != 1 or manifest["status"] != MODIFIED_STATUS or manifest["distribution_status"] != BLOCKED:
        raise ValueError("Blocked modified review envelope required")
    entries = list(kit.rglob("*"))
    if any(p.is_symlink() or not p.resolve().is_relative_to(kit.resolve())
           or not (p.is_file() or p.is_dir()) for p in entries):
        raise ValueError("Unsafe modified envelope entry")
    actual = {p.relative_to(kit).as_posix() for p in entries if p.is_file()}
    files = manifest["files"]
    if actual != set(files) | {MODIFIED_MANIFEST}:
        raise ValueError("Modified envelope has missing/unmanifested files")
    for name, item in files.items():
        target = kit / relative(name)
        if target.stat().st_size != item["size"] or sha_file(target) != item["sha256"]:
            raise ValueError(f"Modified envelope hash/size mismatch: {name}")
    record = json.loads((kit / "modification-record.json").read_text(encoding="utf-8"))
    receipt = verify(kit / "original-kit", record["original_kit_manifest_sha256"])
    base_files = json.loads((kit / "original-kit/kit-manifest.json").read_text(encoding="utf-8"))["files"]
    if set(files) != MODIFIED_EXTRAS | {"original-kit/kit-manifest.json"} | {"original-kit/" + n for n in base_files}:
        raise ValueError("Modified envelope scope forbids app/binary extras")
    variant = record.get("archive_variant")
    if variant is not None and variant != INLINE_VARIANT:
        raise ValueError("Unknown modified archive variant")
    make_record = noticed_record if variant == INLINE_VARIANT else modified_record
    rebuilt, proof = make_record(kit / "original-kit", kit / "native-build-witness.json",
                                     record["native_build_witness_sha256"], record["modification_date"])
    if any(record.get(k) != v for k, v in rebuilt.items()):
        raise ValueError("Modified source record differs from witnessed build")
    archive = kit / "modified-corresponding-source.zip"
    if sha_file(archive) != record["modified_archive_sha256"] or archive.stat().st_size != record["modified_archive_size"]:
        raise ValueError("Modified archive pin mismatch")
    if (kit / "VIRA-MODIFICATIONS.txt").read_bytes() != modification_notice(record).encode("utf-8"):
        raise ValueError("External modification notice differs")
    sources = verify_modified_archive(archive, kit / "original-kit", record, proof)
    result = {"schema": 1, "distribution_status": BLOCKED, "modified_kit_manifest_sha256": expected_manifest_sha256,
            "external_manifest_hash_checked": True, "original_kit_manifest_sha256": receipt["kit_manifest_sha256"],
            "original_archive_sha256": SOURCE_SHA, "modified_archive_sha256": record["modified_archive_sha256"],
            "modified_archive_size": record["modified_archive_size"], "native_build_witness_sha256": record["native_build_witness_sha256"],
            "verified_sources": sources, "licensed_files": receipt["licensed_files"], "kit_files": len(files),
            "new_modified_source_archive_prepared": True, "recipient_source_delivery": False,
            "legal_notice_completeness_approved": False, "modified_build_is_distribution_candidate": False,
            "new_native_build_from_this_envelope_proven": False}
    if variant == INLINE_VARIANT:
        result.update(archive_variant=variant, inline_change_date_notice_present_in_archive_source=True,
                      prior_build_witness_applies_to_archive_sources=False)
    return result



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--extract-sources", type=Path)
    parser.add_argument("--modified-base-kit", type=Path)
    parser.add_argument("--witness", type=Path)
    parser.add_argument("--expected-witness-sha256")
    parser.add_argument("--change-date")
    parser.add_argument("--verify-modified", type=Path)
    parser.add_argument("--inline-notice", action="store_true", help="New source candidate, NOT a prior compiled-source claim")
    args = parser.parse_args()
    if args.modified_base_kit or args.verify_modified:
        if args.archive or args.verify or not args.expected_manifest_sha256:
            parser.error("modified modes require an external manifest digest and no original build/verify flags")
        if args.verify_modified:
            if args.modified_base_kit or args.out or args.witness or args.expected_witness_sha256 or args.change_date or args.inline_notice:
                parser.error("modified verification and assembly must be separate")
            result = verify_modified(args.verify_modified, args.expected_manifest_sha256)
            if args.extract_sources:
                if args.extract_sources.resolve().is_relative_to(args.verify_modified.resolve()):
                    parser.error("extraction must be outside the modified kit")
                extract_archive(args.verify_modified / "modified-corresponding-source.zip", args.extract_sources)
        else:
            if not args.out or not args.witness or not args.expected_witness_sha256 or not args.change_date or args.extract_sources:
                parser.error("modified assembly requires fresh output, authenticated witness and change date")
            result = build_modified(args.modified_base_kit, args.expected_manifest_sha256, args.witness,
                                    args.expected_witness_sha256, args.change_date, args.out, inline_notice=args.inline_notice)
        print(json.dumps(result, indent=2))
        return
    if args.witness or args.expected_witness_sha256 or args.change_date or args.inline_notice:
        parser.error("witness and change date are modified-mode only")
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

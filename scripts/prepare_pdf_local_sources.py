"""Prepare pinned vcpkg overlays using LOCAL preferred sources, not new downloads.

SPDX-License-Identifier: MIT
Copyright (c) 2026 VIRA contributors

MIT build-tooling derivative. Standard library only; no app, runtime publication
or compiler/CRT permission. Build tools/host sources still need network access.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN_FILE = "docs/dependencies/pdf-local-source-port-pins.json"
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
ACQUIRE = re.compile(r"(?im)^[ \t]*(vcpkg_from_[a-z_]+|vcpkg_download_distfile|vcpkg_extract_source_archive)\s*\(")
PCRE_MERGE = '''file(REMOVE_RECURSE "${SOURCE_PATH}/deps/sljit")
file(MAKE_DIRECTORY "${SOURCE_PATH}/deps")
file(RENAME "${SLJIT_SOURCE_PATH}" "${SOURCE_PATH}/deps/sljit")'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def own_kit_tool():
    spec = importlib.util.spec_from_file_location("trusted_pdf_source_kit", ROOT / "scripts/pdf_source_kit.py")
    if spec is None or spec.loader is None:
        raise ValueError("Trusted adjacent source-kit verifier unavailable")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def calls(text: str):
    """Read only pinned acquisition calls; handle quotes/comments and nesting.

    This is deliberately not a general CMake rewriter. Whole-file hashes and
    expected command counts pin the admitted grammar/recipes before rewriting.
    """
    for match in ACQUIRE.finditer(text):
        start = match.start()
        index = match.end()
        depth, quoted, comment, escaped = 1, False, False, False
        while index < len(text) and depth:
            c = text[index]
            if comment:
                comment = c != "\n"
            elif escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = not quoted
            elif not quoted:
                if c == "#":
                    comment = True
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
            index += 1
        if depth:
            raise ValueError("Unbalanced pinned source acquisition")
        yield start, index, match.group(1).lower(), text[match.end():index - 1]


def transformed_port(name: str, text: str, pin: dict) -> str:
    text = text.replace("\r\n", "\n")
    if sha(text.encode()) != pin["port_sha256"]:
        raise ValueError(f"Port recipe changed: {name}")
    spans = list(calls(text))
    if len(spans) != pin["acquisition_calls"]:
        raise ValueError(f"Unexpected source acquisition count: {name}")
    main = 0
    for _, _, command, body in spans:
        if command == "vcpkg_extract_source_archive":
            if not re.match(r"\s*SOURCE_PATH(?:\s|$)", body):
                raise ValueError("Unexpected extraction variable")
            main += 1
        elif command.startswith("vcpkg_from_"):
            variables = re.findall(r"\bOUT_SOURCE_PATH\s+(\w+)", body)
            if variables == ["SOURCE_PATH"]:
                main += 1
            elif name != "pcre2" or variables != ["SLJIT_SOURCE_PATH"]:
                raise ValueError("Unexpected source-acquisition output")
    if main != (0 if name == "pthread" else 1):
        raise ValueError("Exactly one main preferred source expected")
    for start, end, _, _ in reversed(spans):
        text = text[:start] + "# Target source acquisition replaced by verified local preferred tree.\n" + text[end:]
    if name == "pcre2":
        if text.count(PCRE_MERGE) != 1:
            raise ValueError("Pinned PCRE2/SLJIT merge changed")
        text = text.replace(PCRE_MERGE, "# SLJIT is already integrated in the captured PCRE2 preferred tree.")
    if ACQUIRE.search(text):
        raise ValueError("Target source acquisition survived transformation")
    return text


def tree_record(root: Path) -> dict:
    digest = hashlib.sha256()
    links = {}
    count = 0
    base = root.resolve()
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        # Reject junctions/external links, including links introduced in edits.
        if not path.resolve().is_relative_to(base):
            raise ValueError("External preferred-source path")
        if getattr(path, "is_junction", lambda: False)():
            raise ValueError("Junction in preferred sources")
        if path.is_symlink():
            if not path.exists() or path.is_dir():
                raise ValueError(f"Dangling or directory preferred-source symlink: {path}")
            target = os.readlink(path).replace("\\", "/")
            if target.startswith("/") or ":" in target or "\0" in target:
                raise ValueError("Unsafe preferred-source symlink")
            data = target.encode()
            links[relative] = target
            kind = b"symlink"
        elif path.is_file():
            data, kind = path.read_bytes(), b"file"
        elif path.is_dir():
            continue
        else:
            raise ValueError("Special file in preferred sources")
        digest.update(relative.encode() + b"\0" + kind + b"\0" + sha(data).encode() + b"\n")
        count += 1
    return {"patched_source_files": count, "patched_source_tree_sha256": digest.hexdigest(), "patched_source_symlinks": links}


def cmake_path(path: Path) -> str:
    text = path.resolve().as_posix()
    # Explicit supported-path boundary; no executable CMake interpolation in paths.
    if any(c in text for c in '\";$[]\r\n'):
        raise ValueError("Preferred-source path contains unsupported CMake metacharacters")
    return text


def wrapper(name: str, source: Path | None, root_name: str | None) -> str:
    result = '''# SPDX-License-Identifier: MIT
# Copyright (c) 2026 VIRA contributors
# Local target-only adapter; upstream recipe and license are retained beside it.
if(NOT TARGET_TRIPLET STREQUAL "x64-vira-pdf")
    include("${CMAKE_CURRENT_LIST_DIR}/upstream-portfile.cmake")
    return()
endif()
'''
    if name == "libpng":
        result += '''if("apng" IN_LIST FEATURES)
    message(FATAL_ERROR "Local baseline does not include the APNG source patch; use a reviewed custom overlay")
endif()
'''
    if source is not None:
        # Only vcpkg's internal temporary src area is replaced, NEVER the input
        # kit/source tree or an installed VIRA directory. Driver requires new work.
        result += '''file(REMOVE_RECURSE "${CURRENT_BUILDTREES_DIR}/src")
file(MAKE_DIRECTORY "${CURRENT_BUILDTREES_DIR}/src")
'''
        result += f'file(COPY "{cmake_path(source)}" DESTINATION "${{CURRENT_BUILDTREES_DIR}}/src")\n'
        result += f'set(SOURCE_PATH "${{CURRENT_BUILDTREES_DIR}}/src/{root_name}")\n'
    result += 'include("${CMAKE_CURRENT_LIST_DIR}/local-portfile.cmake")\n'
    return result


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")


def prepare(kit: Path, sources: Path, destination: Path, expected_manifest_sha256: str, allow_modified: bool = False) -> dict:
    if destination.exists():
        raise FileExistsError("New overlay directory required; nothing will be overwritten")
    resolved_out = destination.resolve()
    if any(resolved_out.is_relative_to(p.resolve()) for p in (kit, sources)):
        raise ValueError("Overlay output must be outside the source kit and preferred inputs")
    tool = own_kit_tool()
    kit_receipt = tool.verify(kit, expected_manifest_sha256)
    pins = json.loads((ROOT / PIN_FILE).read_text(encoding="utf-8"))
    inventory = json.loads((kit / "evidence/pdf-runtime-win64-source-inventory.json").read_text(encoding="utf-8"))
    if (pins["vcpkg_commit"] != inventory["vcpkg_commit"]
            or pins["source_archive_sha256"] != inventory["source_archive"]["sha256"]
            or set(pins["packages"]) != set(inventory["source_packages"])):
        raise ValueError("Pinned port/source coverage differs")
    reference = copy.deepcopy(inventory)
    records = {}
    archive = zipfile.ZipFile(kit / "corresponding-source.zip")
    try:
        for name, expected in inventory["source_packages"].items():
            pin = pins["packages"][name]
            root = sources / "sources" / name
            if root.is_symlink() or not root.resolve().is_relative_to(sources.resolve()):
                raise ValueError("External preferred-source package root")
            actual = tree_record(root)
            changed = any(actual[k] != expected[k] for k in actual)
            if changed and not allow_modified:
                raise ValueError(f"Preferred source changed; explicit --allow-modified required: {name}")
            roots = sorted(p.name for p in root.iterdir()) if root.is_dir() else []
            if roots != pin["roots"] or (roots and (len(roots) != 1 or not (root / roots[0]).is_dir())):
                raise ValueError(f"Unsupported preferred-source root layout: {name}")
            prefix = f"vcpkg/ports/{name}/"
            recipe_bytes = archive.read(prefix + "portfile.cmake")
            if sha(recipe_bytes) != pin["archived_port_sha256"]:
                raise ValueError(f"Archived port recipe changed: {name}")
            recipe = recipe_bytes.decode("utf-8")
            transformed = transformed_port(name, recipe, pin)
            if roots:
                cmake_path(root / roots[0])
            records[name] = {**actual, "changed_from_original": changed, "original_tree_sha256": expected["patched_source_tree_sha256"],
                             "roots": roots, "upstream_port_sha256": pin["port_sha256"],
                             "transformed_port_sha256": sha(transformed.encode()), "source_path": str(root.resolve())}
            reference["source_packages"][name].update(actual)
        # Validate every input before creating anything at the destination.
        mit_notice = (ROOT / "LICENSES/VIRA-PDF-BUILD-MIT.txt").read_bytes()
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "VIRA-PDF-BUILD-MIT.txt").write_bytes(mit_notice)
        for name, record in records.items():
            port = destination / name
            port.mkdir()
            prefix = f"vcpkg/ports/{name}/"
            for member in archive.namelist():
                if member.startswith(prefix):
                    relative = tool.relative(member[len(prefix):])
                    path = port / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(member))
            original = (port / "portfile.cmake").read_text(encoding="utf-8")
            (port / "upstream-portfile.cmake").write_text(original, encoding="utf-8", newline="\n")
            (port / "local-portfile.cmake").write_text(transformed_port(name, original, pins["packages"][name]), encoding="utf-8", newline="\n")
            source_root = sources / "sources" / name
            roots = record["roots"]
            (port / "portfile.cmake").write_text(wrapper(name, source_root / roots[0] if roots else None, roots[0] if roots else None), encoding="utf-8", newline="\n")
        for upstream, filename in (("vcpkg/LICENSE.txt", "UPSTREAM-VCPKG-LICENSE.txt"), ("vcpkg/NOTICE.txt", "UPSTREAM-VCPKG-NOTICE.txt")):
            if upstream in archive.namelist():
                (destination / filename).write_bytes(archive.read(upstream))
    finally:
        archive.close()
    # An original archive does NOT describe changed preferred-source bytes.
    reference["original_source_archive"] = reference.pop("source_archive")
    reference["source_archive"] = None
    reference["origin"] = "LOCAL_PREFERRED_SOURCE_INPUTS_WITH_EXPLICIT_MODIFICATION_RECORD"
    reference["new_corresponding_source_archive_prepared"] = False
    write_json(destination / "local-source-reference.json", reference)
    result = {"schema": 1, "distribution_status": BLOCKED, "source_kit_manifest_sha256": kit_receipt["kit_manifest_sha256"],
              "target_triplet": "x64-vira-pdf", "host_source_downloads_still_allowed": True,
              "target_source_acquisitions_replaced": True, "modified_sources_explicitly_allowed": allow_modified,
              "packages": records, "changed_packages": [n for n, r in records.items() if r["changed_from_original"]],
              "offline_sdk": False, "new_corresponding_source_archive_prepared": False}
    write_json(destination / "local-source-preparation.json", result)
    return result


def check_inputs(receipt: dict) -> None:
    for name, expected in receipt["packages"].items():
        actual = tree_record(Path(expected["source_path"]))
        if any(actual[k] != expected[k] for k in actual):
            raise ValueError(f"Local input source was mutated during compilation: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-modified", action="store_true")
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--check-inputs", type=Path)
    args = parser.parse_args()
    if args.check_inputs:
        if args.kit or args.sources or args.out or args.allow_modified or args.expected_manifest_sha256:
            parser.error("Input checking is separate from overlay generation")
        check_inputs(json.loads(args.check_inputs.read_text(encoding="utf-8")))
        print("PASS: local preferred-source inputs unchanged")
    else:
        if not args.kit or not args.sources or not args.out or not args.expected_manifest_sha256:
            parser.error("--kit, --sources, --out and --expected-manifest-sha256 are required")
        result = prepare(args.kit, args.sources, args.out, args.expected_manifest_sha256, args.allow_modified)
        print(json.dumps({"packages": len(result["packages"]), "changed_packages": result["changed_packages"],
                          "distribution_status": BLOCKED}, indent=2))


if __name__ == "__main__":
    main()

"""Native-only build and compiler-term evidence; no application or legal approval.

SPDX-License-Identifier: MIT
Copyright (c) 2026 VIRA contributors
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path

BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compiler_evidence(root: Path, facts: dict) -> dict:
    records = []
    for file in sorted(root.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in {".txt", ".log", ".json", ".cmake"}:
            continue
        if "detect_compiler" not in file.parts or file.stat().st_size > 16 * 1024 * 1024:
            continue
        data = file.read_bytes()
        text = data.decode("utf-8", errors="replace")
        lines = [line[:1200] for line in text.splitlines() if re.search(
            r"(compiler identification|compiler version|MSVC|cl\.exe|Windows SDK|WindowsSDK|CMAKE_.*COMPILER|VCTools)", line, re.I)]
        if lines:
            records.append({"path": file.relative_to(root).as_posix(), "sha256": sha(data),
                            "matching_line_count": len(lines), "lines": lines[:30],
                            "lines_truncated": len(lines) > 30})
    if not records:
        raise ValueError("No actual compiler-detection records; cannot infer native compiler from Python")
    licenses = []
    for name in facts.get("license_files", []):
        file = Path(name)
        data = file.read_bytes()
        licenses.append({"path": str(file), "sha256": sha(data), "size": len(data),
                         "preview": data[:16000].decode("utf-8", errors="replace"),
                         "preview_truncated": len(data) > 16000})
    return {"schema": 1, "distribution_status": BLOCKED, "compiler_detection_records": records,
            "current_runner_facts": facts, "installed_license_evidence": licenses,
            "legal_status": "EVIDENCE_ONLY_NOT_PERMISSION_OR_LEGAL_APPROVAL",
            "no_installed_license_candidates": not bool(licenses),
            "compiler_crt_terms_review_status": "PENDING_APPLICABLE_TERMS_AND_LICENSE_ENTITLEMENT_REVIEW",
            "original_vs_new_compiler_identity_requires_comparison": True}


def audit_build(sidecar: Path, work: Path, reference: dict) -> dict:
    if any((sidecar / name).exists() for name in ("backend", "frontend", "pyproject.toml", "uv.lock", ".git")):
        raise ValueError("Not an isolated native-only sidecar")
    sys.path.insert(0, str(sidecar / "scripts"))
    import source_pdf_inventory as source
    from pdf_runtime_inventory import dependency_closure

    if not Path(source.__file__).resolve().is_relative_to(sidecar.resolve()):
        raise ValueError("Collector imported from outside the isolated sidecar")
    installed = work / "installed"
    result = json.loads((work / "rebuild-result.json").read_text(encoding="utf-8"))
    if (result["distribution_status"] != BLOCKED or result["application_required"] is not False
            or result["binary_cache"] != "DISABLED" or result["vcpkg_commit"] != reference["vcpkg_commit"]):
        raise ValueError("Unexpected build provenance")
    packages, owners = source.package_records(installed)
    if set(packages) != set(reference["source_packages"]):
        raise ValueError("Target package set changed")
    verified = {}
    for name, expected in sorted(reference["source_packages"].items()):
        tree = work / "vcpkg/buildtrees" / name / "src"
        entries = list(source.tree_entries(tree)) if tree.is_dir() else []
        digest = hashlib.sha256()
        for path, relative in entries:
            data = source.link_target(path, tree).encode() if path.is_symlink() else path.read_bytes()
            kind = b"symlink" if path.is_symlink() else b"file"
            digest.update(relative.encode() + b"\0" + kind + b"\0" + sha(data).encode() + b"\n")
        if len(entries) != expected["patched_source_files"] or digest.hexdigest() != expected["patched_source_tree_sha256"]:
            raise ValueError(f"Patched preferred-source tree differs from original: {name}")
        verified[name] = {"source_entries": len(entries), "tree_sha256": digest.hexdigest()}
    native = installed / source.TRIPLET / "bin"
    files = {file.name.lower(): file.read_bytes() for file in native.glob("*.dll")}
    roots = tuple(source.choose(files, aliases) for aliases in source.ROOT_ALIASES)
    closure = dependency_closure(files, roots=roots)
    if set(closure) != set(reference["dlls"]):
        raise ValueError("Native PE dependency closure differs from original")
    if sys.platform != "win32":
        raise ValueError("Actual native DLL loading requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel.GetModuleFileNameW.restype = ctypes.c_uint32
    loaded = {}
    with __import__("os").add_dll_directory(str(native)):
        for name in sorted(closure):
            owner = owners.get(f"{source.TRIPLET}/bin/{name}".casefold())
            if owner != reference["dlls"][name]["source_package"]:
                raise ValueError(f"Native owner changed: {name}")
            library = ctypes.CDLL(str(native / name))
            buffer = ctypes.create_unicode_buffer(32768)
            size = kernel.GetModuleFileNameW(library._handle, buffer, len(buffer))
            if not size or Path(buffer.value).resolve() != (native / name).resolve():
                raise ValueError(f"Foreign native origin: {name}")
            loaded[name] = {"source_package": owner, "sha256": sha(files[name]), "loaded_path": buffer.value}
    return {"schema": 1, "distribution_status": BLOCKED, "application_present": False,
            "native_compilation": "SUCCESS", "preferred_source_trees": verified,
            "dll_count": len(loaded), "dlls": loaded,
            "not_proven": ["application PDF rendering with this new build", "bitwise reproducibility",
                           "compiler/CRT redistribution permission", "production installation/updates"]}


def emit(path: Path, group: int) -> None:
    if not 0 <= group < 4:
        raise ValueError("Invalid evidence group")
    data = base64.b64encode(zlib.compress(path.read_bytes())).decode()
    chunks = [data[i:i + 3000] for i in range(0, len(data), 3000)]
    if len(chunks) > 32:
        raise ValueError("Evidence needs more steps; refusing truncation")
    for i in range(group * 8, min((group + 1) * 8, len(chunks))):
        record = json.dumps({"part": i, "total": len(chunks), "data": chunks[i]})
        print(f"::notice title=Native recipe evidence::{record}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--compiler-root", type=Path)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--emit-group", type=int)
    args = parser.parse_args()
    if args.emit_group is not None:
        emit(args.out, args.emit_group)
        return
    if args.compiler_root:
        result = compiler_evidence(args.compiler_root, json.loads(args.facts.read_text(encoding="utf-8-sig")))
    else:
        result = audit_build(args.sidecar, args.work, json.loads(args.reference.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("PASS: evidence only; " + BLOCKED)


if __name__ == "__main__":
    main()

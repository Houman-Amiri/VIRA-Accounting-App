"""Audit a pinned upstream Windows PDF runtime; private test candidates only.

A dependency closure and a PE version string are NOT a license/source approval.
No native binaries from this tool may enter a public installer/delta yet.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pefile

SDK_SHA256 = "ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53"
SDK_URL = "https://github.com/Kozea/WeasyPrint/releases/download/v70.0/weasyprint-windows-onedir.zip"
ROOTS = (
    "libgobject-2.0-0.dll", "libpango-1.0-0.dll", "libharfbuzz-0.dll",
    "libfontconfig-1.dll", "libpangoft2-1.0-0.dll", "libharfbuzz-subset-0.dll",
)
# Windows 10+ inbox DLLs only. In particular MSVCP/VCRUNTIME/libgcc/libstdc++
# are NOT assumed to exist on a clean user machine.
SYSTEM_DLLS = frozenset((
    "advapi32.dll", "avrt.dll", "bcrypt.dll", "cfgmgr32.dll", "comctl32.dll",
    "comdlg32.dll", "crypt32.dll", "d2d1.dll", "dnsapi.dll", "dwmapi.dll",
    "dwrite.dll", "gdi32.dll", "imm32.dll", "iphlpapi.dll", "kernel32.dll",
    "mpr.dll", "msimg32.dll", "msvcrt.dll", "netapi32.dll", "normaliz.dll",
    "ntdll.dll", "ole32.dll", "oleaut32.dll", "powrprof.dll", "propsys.dll",
    "psapi.dll", "rpcrt4.dll", "secur32.dll", "setupapi.dll", "shell32.dll",
    "shcore.dll", "shlwapi.dll", "ucrtbase.dll", "user32.dll", "userenv.dll",
    "usp10.dll", "uxtheme.dll", "version.dll", "winhttp.dll", "wininet.dll",
    "winmm.dll", "winspool.drv", "wintrust.dll", "ws2_32.dll", "wldap32.dll",
))
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"


def dll_name(name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_.+-]+\.(dll|drv)", name, re.I):
        raise ValueError(f"Unsafe native import name: {name!r}")
    return name.lower()


def is_system(name: str) -> bool:
    name = dll_name(name)
    return name in SYSTEM_DLLS or name.startswith(("api-ms-win-", "ext-ms-win-"))


def inspect_pe(data: bytes) -> dict:
    """Read imports/resources without executing any library."""
    with pefile.PE(data=data, fast_load=True) as pe:
        if pe.FILE_HEADER.Machine != 0x8664 or not pe.FILE_HEADER.Characteristics & 0x2000:
            raise ValueError("An x64 PE DLL is required")
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"],
        ])
        imports = sorted({
            dll_name(entry.dll.decode("ascii"))
            for category in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
            for entry in getattr(pe, category, [])
        })
        versions = {}
        for group in getattr(pe, "FileInfo", []):
            for info in group:
                if getattr(info, "Key", None) == b"StringFileInfo":
                    for table in info.StringTable:
                        for key in (b"FileVersion", b"ProductVersion", b"CompanyName", b"ProductName", b"LegalCopyright"):
                            if key in table.entries:
                                versions[key.decode()] = table.entries[key].decode("utf-8", errors="replace")
        return {"machine": "AMD64", "imports": imports, "version_resource": versions}


def dependency_closure(
    files: dict[str, bytes], *, roots: tuple[str, ...] = ROOTS,
    inspector: Callable[[bytes], dict] = inspect_pe,
) -> dict[str, dict]:
    """Resolve exclusively within the archive, never PATH/System32/MSYS installs."""
    normalized = {}
    for name, data in files.items():
        key = dll_name(name)
        if key in normalized:
            raise ValueError(f"Case-colliding DLL: {name}")
        normalized[key] = data
    pending = list(roots)
    selected: dict[str, dict] = {}
    while pending:
        name = dll_name(pending.pop())
        if is_system(name) or name in selected:
            continue
        if name not in normalized:
            raise ValueError(f"Unresolved non-system DLL: {name}")
        if re.fullmatch(r"python\d+(_d)?\.dll", name):
            raise ValueError("Python ABI DLL must not be part of the native text runtime")
        data = normalized[name]
        metadata = inspector(data)
        imports = sorted({dll_name(n) for n in metadata["imports"]})
        selected[name] = {
            **metadata, "imports": imports, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "system_imports": [n for n in imports if is_system(n)],
            "bundled_imports": [n for n in imports if not is_system(n)],
            "license_and_source_status": "UNREVIEWED",
        }
        pending.extend(n for n in imports if not is_system(n))
    return dict(sorted(selected.items()))


def build_candidate(archive: Path, output: Path) -> dict:
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SDK_SHA256:
        raise ValueError("Pinned upstream SDK SHA256 mismatch")
    if output.exists():
        raise ValueError("Candidate output must not already exist")
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.namelist()
        matches = [n for n in members if PurePosixPath(n).name == ROOTS[1]]
        if len(matches) != 1:
            raise ValueError("Expected a unique upstream native DLL directory")
        parent = PurePosixPath(matches[0]).parent
        names = [n for n in members if PurePosixPath(n).parent == parent and n.lower().endswith(".dll")]
        files = {}
        for name in names:
            key = dll_name(PurePosixPath(name).name)
            if key in files:
                raise ValueError("Duplicate archive DLL name")
            files[key] = zipped.read(name)
        closure = dependency_closure(files)
    manifest = {
        "format": 1, "platform": "windows-x64", "minimum_windows": "10",
        "distribution_status": BLOCKED,
        "upstream": {"url": SDK_URL, "sha256": SDK_SHA256},
        "roots": list(ROOTS), "dlls": closure,
        "excluded_upstream_dll_count": len(files) - len(closure),
        "review_notes": [
            "PE version strings are not verified source/build provenance.",
            "PE imports do not identify arbitrary LoadLibrary/plugin dependencies; rendering is tested separately.",
            "Upstream WeasyPrint's own license does not license every native dependency.",
            "Exact source versions, build patches, license texts and corresponding source remain required.",
        ],
    }
    (output / "bin").mkdir(parents=True)
    for name in closure:
        (output / "bin" / name).write_bytes(files[name])
    (output / "runtime-inventory.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    (output / "DO_NOT_DISTRIBUTE.txt").write_text(
        BLOCKED + "\nPrivate CI candidate only. Not an approved installer/delta runtime.\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_candidate(args.archive, args.out_dir)
    print(json.dumps({"dll_count": len(result["dlls"]), "excluded": result["excluded_upstream_dll_count"],
                      "distribution_status": BLOCKED}))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # GitHub truncates annotations at 4096 characters and caps their count.
        # Compressed ASCII chunks preserve the full audit without log redirects.
        payload = base64.b64encode(zlib.compress(json.dumps(result, ensure_ascii=True).encode())).decode()
        chunks = [payload[i:i + 3000] for i in range(0, len(payload), 3000)]
        for index, chunk in enumerate(chunks):
            record = json.dumps({"part": index, "total": len(chunks), "data": chunk})
            print(f"::notice title=PDF native inventory chunk::{record}")


if __name__ == "__main__":
    main()

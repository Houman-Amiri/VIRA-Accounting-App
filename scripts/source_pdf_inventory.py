"""Capture source/recipe/license evidence for a private vcpkg native build.

Never grants distribution approval. Compiler/bootstrap tools are recorded build
prerequisites, not claimed as source-built or included in the native runtime.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import zipfile
import zlib
from pathlib import Path

from pdf_runtime_inventory import BLOCKED, dependency_closure

TRIPLET = "x64-vira-pdf"
ROOT_ALIASES = (
    ("libgobject-2.0-0.dll", "gobject-2.0-0.dll"),
    ("libpango-1.0-0.dll", "pango-1.0-0.dll"),
    ("libharfbuzz-0.dll", "harfbuzz.dll"),
    ("libfontconfig-1.dll", "fontconfig-1.dll"),
    ("libpangoft2-1.0-0.dll", "pangoft2-1.0-0.dll"),
    ("libharfbuzz-subset-0.dll", "harfbuzz-subset.dll"),
)
FFI_ALIASES = ("libffi-8.dll", "ffi-8.dll", "ffi.dll", "libffi.dll")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def choose(files: dict, aliases: tuple[str, ...]) -> str:
    matches = [name for name in aliases if name in files]
    if len(matches) != 1:
        raise ValueError(f"Exactly one native implementation required: {aliases}: {matches}")
    return matches[0]


def package_records(installed: Path, triplet: str = TRIPLET) -> tuple[dict, dict]:
    """Ownership comes from installed package receipts, never guessed DLL names."""
    packages: dict = {}
    owners: dict = {}
    for receipt in sorted((installed / "vcpkg/info").glob(f"*_{triplet}.list")):
        name = receipt.name.split("_", 1)[0]
        paths = receipt.read_text(encoding="utf-8").splitlines()
        packages[name] = {"receipt": receipt.name, "files": paths}
        for path in paths:
            if path.endswith("/"):
                continue
            normalized = path.replace("\\", "/").casefold()
            if normalized in owners:
                raise ValueError(f"Duplicate package owner: {path}")
            owners[normalized] = name
    if not packages:
        raise ValueError("No installed target package receipts")
    return packages, owners


def tree_entries(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Uncaptured symlink in corresponding source: {path}")
        if path.is_file():
            yield path, path.relative_to(root).as_posix()


def capture_sources(vcpkg: Path, installed: Path, packages: dict, archive: Path, profile: Path) -> dict:
    """Keep complete patched src trees, full immutable recipes and license notices.

    No binary cache, buildtrees outside src, downloaded executables or installed
    DLLs are copied. This is corresponding-source evidence, NOT an offline SDK.
    """
    evidence = {}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for directory in ("ports", "scripts", "triplets", "versions"):
            for path, relative in tree_entries(vcpkg / directory):
                bundle.write(path, f"vcpkg/{directory}/{relative}")
        for name in ("LICENSE.txt", "NOTICE.txt", ".vcpkg-root", "bootstrap-vcpkg.bat", "bootstrap-vcpkg.sh"):
            path = vcpkg / name
            if path.is_file():
                bundle.write(path, f"vcpkg/{name}")
        for path, relative in tree_entries(profile):
            bundle.write(path, f"vira-recipe/{relative}")
        for name, package in packages.items():
            share = installed / TRIPLET / "share" / name
            copyright_file, spdx_file = share / "copyright", share / "vcpkg.spdx.json"
            if not copyright_file.is_file() or not copyright_file.stat().st_size or not spdx_file.is_file():
                raise ValueError(f"Missing copyright/SPDX evidence: {name}")
            spdx = json.loads(spdx_file.read_text(encoding="utf-8"))
            entries = spdx.get("packages", [])
            source = vcpkg / "buildtrees" / name / "src"
            source_files = list(tree_entries(source)) if source.is_dir() else []
            has_native_code = any(p.lower().endswith((".dll", ".lib", ".a")) for p in package["files"])
            if has_native_code and not source_files:
                raise ValueError(f"Native library has no captured source tree: {name}")
            tree_hash = hashlib.sha256()
            for path, relative in source_files:
                # Complete, patched upstream source, not a filtered extension list.
                data = path.read_bytes()
                tree_hash.update(relative.encode("utf-8") + b"\0" + digest(data).encode() + b"\n")
                bundle.writestr(f"sources/{name}/{relative}", data)
            for path, relative in tree_entries(share):
                bundle.write(path, f"installed-notices/{name}/{relative}")
            evidence[name] = {
                "receipt": package["receipt"], "native_code": has_native_code,
                "patched_source_files": len(source_files), "patched_source_tree_sha256": tree_hash.hexdigest(),
                "copyright_sha256": digest(copyright_file.read_bytes()),
                "spdx_sha256": digest(spdx_file.read_bytes()),
                "spdx_packages": entries,
                "source_status": "PATCHED_TREE_CAPTURED" if source_files else "RECIPE_ONLY_NO_NATIVE_CODE",
            }
        bundle.writestr("README.txt", (
            "VIRA private native source evidence. NOT a distribution approval.\n"
            "sources/ contains complete patched source trees for target packages.\n"
            "vcpkg/ contains immutable recipes, patches and tool-download hashes.\n"
            "installed-notices/ contains upstream copyright and SPDX records.\n"
            "vira-recipe/ describes the target, baseline and rebuilding steps.\n"
            "This is NOT an offline compiler SDK or a bit-for-bit reproducibility claim.\n"
            "MSVC/Windows SDK, bootstrap executables and build tools are prerequisites.\n"
            "Source and build prerequisites can have different licenses. Review is still required.\n"
        ))
    return evidence


def build(vcpkg: Path, installed: Path, out: Path, reports: Path, profile: Path) -> dict:
    pin = json.loads((profile / "vcpkg.json").read_text())["builtin-baseline"]
    files = {}
    for path in sorted((installed / TRIPLET / "bin").glob("*.dll")):
        key = path.name.lower()
        if key in files:
            raise ValueError(f"Case-colliding DLL: {path.name}")
        files[key] = path.read_bytes()
    roots = tuple(choose(files, aliases) for aliases in ROOT_ALIASES)
    closure = dependency_closure(files, roots=roots)
    ffi = choose(closure, FFI_ALIASES)
    packages, owners = package_records(installed)
    for name, item in closure.items():
        owner = owners.get(f"{TRIPLET}/bin/{name}".casefold())
        if not owner:
            raise ValueError(f"DLL has no installed package owner: {name}")
        item["source_package"] = owner
        item["license_and_source_status"] = "SOURCE_CAPTURED_PENDING_LICENSE_REVIEW"
    reports.mkdir(parents=True, exist_ok=True)
    source_zip = reports / "corresponding-source.zip"
    evidence = capture_sources(vcpkg, installed, packages, source_zip, profile)
    inventory = {
        "schema": 1, "distribution_status": BLOCKED,
        "origin": "LOCAL_PINNED_VCPKG_SOURCE_BUILD",
        "vcpkg_commit": pin, "triplet": TRIPLET, "binary_cache": "DISABLED",
        "roots": list(roots), "preload_dlls": [ffi], "dlls": closure,
        "excluded_dlls": sorted(files.keys() - closure.keys()),
        "total_bytes": sum(len(files[name]) for name in closure),
        "source_archive": {"name": source_zip.name, "sha256": digest(source_zip.read_bytes()), "size": source_zip.stat().st_size},
        "source_packages": evidence,
        "open_gates": ["LICENSE_CHOICES_AND_NOTICES_REVIEW", "COMPILER_CRT_TERMS_REVIEW", "PRODUCTION_BOOTSTRAP_AND_UPDATES", "INSTALLED_USER_ACCEPTANCE"],
    }
    (out / "bin").mkdir(parents=True, exist_ok=True)
    for name in closure:
        (out / "bin" / name).write_bytes(files[name])
    text = json.dumps(inventory, ensure_ascii=False, indent=2) + "\n"
    (out / "runtime-inventory.json").write_text(text, encoding="utf-8")
    (out / "DO_NOT_DISTRIBUTE.txt").write_text(BLOCKED + "\n", encoding="utf-8")
    (reports / "source-inventory.json").write_text(text, encoding="utf-8")
    # Capture the actual generated toolchain configuration and installed receipts.
    for source, destination in ((vcpkg / "buildtrees", reports / "toolchains"), (installed / "vcpkg/info", reports / "receipts")):
        for path in source.rglob("*"):
            if path.is_file() and (source.name == "info" or path.name.startswith(("vcpkg_abi_info", "vcpkg_cmake", "vcpkg_meson", "config-")) and path.suffix in (".txt", ".log", ".ini", ".cmake")):
                dest = destination / path.relative_to(source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
    payload = base64.b64encode(zlib.compress(json.dumps(inventory, ensure_ascii=True).encode())).decode()
    chunks = [payload[i:i + 3000] for i in range(0, len(payload), 3000)]
    for index, chunk in enumerate(chunks):
        record = json.dumps({"part": index, "total": len(chunks), "data": chunk})
        print(f"::notice title=Source PDF inventory chunk::{record}")
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("vcpkg-root", "installed", "out-dir", "reports"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    build(args.vcpkg_root, args.installed, args.out_dir, args.reports, Path("native/pdf-source"))


if __name__ == "__main__":
    main()

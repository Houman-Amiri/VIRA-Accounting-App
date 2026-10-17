"""Verify an existing successful source-proof artifact, without recompiling DLLs.

Metadata extraction is separate because GitHub caps notices at ten per step.
No legal approval, native binaries, release, or installed-user acceptance here.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import stat
import zipfile
import zlib
from pathlib import Path, PureWindowsPath

from pdf_native_smoke import DIGITS, inspect_pdf
from pdf_runtime_inventory import BLOCKED

HASH_FORMAT = "UTF8_POSIX_PATH_NUL_KIND_NUL_SHA256_LF_CASE_SENSITIVE_V1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_run(actual: dict, expected: dict) -> None:
    if (actual.get("id") != expected["run_id"] or actual.get("head_sha") != expected["head_sha"]
            or actual.get("path") != expected["workflow_path"] or actual.get("conclusion") != "success"):
        raise ValueError("Only the exact successful source-build run is admissible")


def verify_sources(inventory: dict, archive: Path) -> dict:
    if inventory["origin"] != "LOCAL_PINNED_VCPKG_SOURCE_BUILD" or inventory["distribution_status"] != BLOCKED:
        raise ValueError("Unexpected provenance or distribution approval")
    if inventory["source_tree_hash_format"] != HASH_FORMAT:
        raise ValueError("Unknown source tree hash format")
    if sha(archive.read_bytes()) != inventory["source_archive"]["sha256"] or archive.stat().st_size != inventory["source_archive"]["size"]:
        raise ValueError("Source archive hash/size mismatch")
    counts = {"packages": 0, "source_files": 0, "source_symlinks": 0}
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or bundle.testzip() is not None:
            raise ValueError("Duplicate or corrupt source archive entries")
        for name, package in inventory["source_packages"].items():
            prefix = f"sources/{name}/"
            entries = sorted(n for n in names if n.startswith(prefix))
            tree_hash = hashlib.sha256()
            links = {}
            for entry in entries:
                relative = entry[len(prefix):]
                data = bundle.read(entry)
                is_link = stat.S_ISLNK(bundle.getinfo(entry).external_attr >> 16)
                kind = b"symlink" if is_link else b"file"
                if is_link:
                    links[relative] = data.decode("utf-8")
                tree_hash.update(relative.encode("utf-8") + b"\0" + kind + b"\0" + sha(data).encode() + b"\n")
            if len(entries) != package["patched_source_files"] or tree_hash.hexdigest() != package["patched_source_tree_sha256"] or links != package["patched_source_symlinks"]:
                raise ValueError(f"Preferred-source tree mismatch: {name}")
            copyright_name = f"installed-notices/{name}/copyright"
            if package["copyright_sha256"] is not None:
                data = bundle.read(copyright_name)
                text = data.decode("utf-8", errors="replace")
                if (sha(data) != package["copyright_sha256"] or text != package["copyright_text"]
                        or (text.encode("utf-8") == data) != package["copyright_text_utf8_lossless"]):
                    raise ValueError(f"Copyright bytes/preview mismatch: {name}")
            elif package["source_status"] != "EMPTY_DEPENDENCY_ALIAS_NO_RUNTIME_FILES" or not package["delegated_license_packages"]:
                raise ValueError(f"Missing native copyright: {name}")
            spdx = bundle.read(f"installed-notices/{name}/vcpkg.spdx.json")
            if sha(spdx) != package["spdx_sha256"] or json.loads(spdx)["packages"] != package["spdx_packages"]:
                raise ValueError(f"SPDX mismatch: {name}")
            selected = sorted(dll for dll, item in inventory["dlls"].items() if item["source_package"] == name)
            if selected != package["selected_dlls"]:
                raise ValueError(f"DLL ownership mismatch: {name}")
            counts["packages"] += 1
            counts["source_files"] += len(entries)
            counts["source_symlinks"] += len(links)
        for dll, item in inventory["dlls"].items():
            owner = inventory["source_packages"][item["source_package"]]
            if owner["source_status"] != "PATCHED_TREE_CAPTURED" or dll not in owner["selected_dlls"]:
                raise ValueError(f"Native owner lacks captured source: {dll}")
    return counts


def verify_worker(worker: dict, inventory: dict) -> None:
    if not all(worker.get(key) for key in ("isolated", "development_dependencies_absent", "ctypes_callbacks_verified")) or worker["distribution_status"] != BLOCKED:
        raise ValueError("Unsuccessful isolated staged interpreter proof")
    native = PureWindowsPath(worker["python"]).parent.parent / "native/pdf/bin"
    if not set(inventory["roots"]) <= worker["loaded_dlls"].keys():
        raise ValueError("Missing loaded core DLL")
    for name, filename in worker["loaded_dlls"].items():
        path = PureWindowsPath(filename)
        if name not in inventory["dlls"] or path.parent != native or path.name.lower() != name:
            raise ValueError("Foreign native module origin")


def emit_chunks(inventory: dict, group: int, per_step: int = 8) -> None:
    payload = base64.b64encode(zlib.compress(json.dumps(inventory, ensure_ascii=True).encode())).decode()
    chunks = [payload[i:i + 3000] for i in range(0, len(payload), 3000)]
    if len(chunks) > 48:
        raise ValueError("Evidence needs more annotation steps; never silently truncate")
    for index in range(group * per_step, min((group + 1) * per_step, len(chunks))):
        record = json.dumps({"part": index, "total": len(chunks), "data": chunks[index]})
        print(f"::notice title=Verified source inventory chunk::{record}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--emit-group", type=int)
    parser.add_argument("--out", type=Path, default=Path("reports/source-evidence"))
    args = parser.parse_args()
    if args.emit_group is not None:
        emit_chunks(json.loads((args.out / "verified-inventory.json").read_text()), args.emit_group)
        return
    expected = json.loads(Path("docs/dependencies/pdf-source-proof-run.json").read_text())
    validate_run(json.loads(args.run.read_text()), expected)
    inv_file = next(args.artifact.rglob("source-inventory.json"))
    inventory = json.loads(inv_file.read_text())
    if inventory["vira_commit"] != expected["head_sha"]:
        raise ValueError("Source inventory belongs to another producer commit")
    counts = verify_sources(inventory, inv_file.parent / "corresponding-source.zip")
    proof_file = next(args.artifact.rglob("bundled-proof.json"))
    proof = json.loads(proof_file.read_text())
    verify_worker(proof["worker"], inventory)
    for name, minimum in (("single-page", 1), ("multi-page", 2)):
        actual = inspect_pdf((proof_file.parent / f"{name}.pdf").read_bytes(), expected_digits=DIGITS, min_pages=minimum)
        if actual != proof["documents"][name]:
            raise ValueError(f"PDF evidence mismatch: {name}")
    if proof["dll_count"] != len(inventory["dlls"]):
        raise ValueError("Native count mismatch")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "verified-inventory.json").write_text(json.dumps(inventory, ensure_ascii=True, indent=2) + "\n")
    summary = {"producer": expected, "verified_source_materials": counts, "dll_count": len(inventory["dlls"]),
               "total_bytes": inventory["total_bytes"], "source_archive": inventory["source_archive"], "proof": proof}
    (args.out / "verified-summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n")
    encoded = base64.b64encode(zlib.compress(json.dumps(summary, ensure_ascii=True).encode())).decode()
    if len(encoded) > 3800:
        raise ValueError("Summary exceeds annotation budget; split into another step")
    print(f"::notice title=Verified source proof summary::{encoded}")


if __name__ == "__main__":
    main()

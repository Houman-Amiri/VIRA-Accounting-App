"""Private app QA adapter: consume an audited local native build, never release it.

This application-test harness is NOT added to the limited native-build MIT grant.
The standalone native recipe remains independent of application dependencies.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from pdf_runtime_inventory import BLOCKED, dependency_closure

BASELINE = "a5f736224e85b32e25a8ffc52562333180396642"
TRIPLET = "x64-vira-pdf"
EXPECTED_VERSION = "1.58.0-vira-local-source"


def prepare(work: Path, reference_path: Path, proof_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("New private consumer candidate directory required")
    if any(output.resolve().is_relative_to(p.resolve()) for p in (work, reference_path.parent, proof_path.parent)):
        raise ValueError("Consumer output must be outside native build/reference/evidence inputs")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    if (reference["vcpkg_commit"] != BASELINE or reference["distribution_status"] != BLOCKED
            or reference["source_archive"] is not None
            or reference["new_corresponding_source_archive_prepared"] is not False
            or proof["distribution_status"] != BLOCKED
            or proof["native_compilation"] != "SUCCESS" or proof["local_preferred_source_replay"] != "SUCCESS"
            or proof["changed_packages"] != ["pango"]
            or proof["actual_pango_version_string"] != EXPECTED_VERSION
            or proof["input_source_trees_unchanged_during_compilation"] is not True
            or proof["dll_count"] != 21 or len(proof["dlls"]) != 21
            or len(reference["source_packages"]) != 20
            or set(proof["preferred_source_trees"]) != set(reference["source_packages"])):
        raise ValueError("Fresh blocked local-build evidence/reference required")
    for name, package in reference["source_packages"].items():
        actual = proof["preferred_source_trees"][name]
        if (actual["source_entries"] != package["patched_source_files"]
                or actual["tree_sha256"] != package["patched_source_tree_sha256"]):
            raise ValueError(f"Source reference differs from actual native audit: {name}")
    native = work / "installed" / TRIPLET / "bin"
    files = {}
    for path in native.glob("*.dll"):
        if path.is_symlink() or path.resolve().parent != native.resolve():
            raise ValueError("Foreign/symlinked candidate DLL")
        name = path.name.lower()
        if name in files:
            raise ValueError("Case-colliding native DLL")
        files[name] = path.read_bytes()
    closure = dependency_closure(files, roots=tuple(reference["roots"]))
    if set(closure) != set(proof["dlls"]) or set(closure) != set(reference["dlls"]):
        raise ValueError("Consumer PE closure differs from fresh native audit")
    for name, item in closure.items():
        audited = proof["dlls"][name]
        if (item["sha256"] != audited["sha256"]
                or Path(audited["loaded_path"]).resolve() != (native / name).resolve()
                or audited["source_package"] != reference["dlls"][name]["source_package"]):
            raise ValueError(f"Consumer DLL hash/origin/owner differs from native audit: {name}")
        item["source_package"] = audited["source_package"]
        item["license_and_source_status"] = "PRIVATE_LOCAL_BUILD_CONSUMER_PROOF_NOT_DISTRIBUTION_CLEARANCE"
    if not reference["preload_dlls"] or not set(reference["preload_dlls"]) <= closure.keys():
        raise ValueError("Audited FFI preload must belong to the candidate")
    inventory = copy.deepcopy(reference)
    inventory.update(origin="LOCAL_PINNED_VCPKG_SOURCE_BUILD", preferred_input_mode="LOCAL_CAPTURED_PATCHED_SOURCES",
                     triplet=TRIPLET, binary_cache="DISABLED", dlls=closure,
                     total_bytes=sum(len(files[name]) for name in closure),
                     private_consumption_only=True, modified_build_is_distribution_candidate=False,
                     expected_pango_version_string=EXPECTED_VERSION,
                     native_audit_sha256=hashlib.sha256(proof_path.read_bytes()).hexdigest(),
                     modified_reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest())
    output.mkdir(parents=True, exist_ok=False)
    (output / "bin").mkdir()
    for name in closure:
        (output / "bin" / name).write_bytes(files[name])
    (output / "runtime-inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "DO_NOT_DISTRIBUTE.txt").write_text(BLOCKED + "\n", encoding="utf-8", newline="\n")
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "reference", "native-proof", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.work, args.reference, args.native_proof, args.out)
    print(json.dumps({"dll_count": len(result["dlls"]), "distribution_status": BLOCKED,
                      "expected_pango_version_string": EXPECTED_VERSION}))


if __name__ == "__main__":
    main()

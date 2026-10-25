"""External private native-target audit adapter, NOT a distribution license grant.

Same authenticated preferred sources, genuinely different compiler code generation.
No PE byte edits, dummy DLLs, source-version markers or audit-hash substitutions.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merge_audits(baseline: dict, fresh: dict) -> dict:
    if (
        baseline["native_compilation"] != "SUCCESS"
        or baseline["local_preferred_source_replay"] != "SUCCESS"
        or baseline["distribution_status"]
        != "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
        or fresh["native_compilation"] != "SUCCESS"
        or fresh["application_present"] is not False
        or fresh["distribution_status"] != baseline["distribution_status"]
        or fresh["preferred_source_trees"] != baseline["preferred_source_trees"]
        or len(fresh["preferred_source_trees"]) != 20
        or fresh["dll_count"] != 21
        or set(fresh["dlls"]) != set(baseline["dlls"])
        or len(fresh["dlls"]) != 21
        or any(
            fresh["dlls"][n]["source_package"] != baseline["dlls"][n]["source_package"]
            for n in fresh["dlls"]
        )
    ):
        raise ValueError("Independent target audit/source/owner closure differs")
    result = copy.deepcopy(baseline)
    result.update(copy.deepcopy(fresh))
    return result


def codegen_evidence(before: bytes, after: bytes, compiler_files: list[tuple[str, bytes]]) -> dict:
    import pefile

    sections = []
    for data in (before, after):
        pe = pefile.PE(data=data, fast_load=True)
        try:
            text = [s.get_data() for s in pe.sections if s.Name.rstrip(b"\0") == b".text"]
            if len(text) != 1 or not text[0]:
                raise ValueError("Exactly one nonempty PE executable text section required")
            sections.append(text[0])
        finally:
            pe.close()
    if sections[0] == sections[1]:
        raise ValueError("Native executable code unchanged; timestamps/metadata are insufficient")
    commands = []
    for name, data in compiler_files:
        text = data.decode("utf-8")
        # Pango's actual generated Ninja compilation instructions, not our recipe
        # comment or a fabricated stamp. Preserve whole files in the CI artifact.
        if "pango-utils.c" in text and all(flag in text for flag in ("/Od", "/Ob0", "/DNDEBUG")):
            commands.append(dict(path=name, sha256=sha(data), bytes=len(data)))
    if not commands:
        raise ValueError("Actual Pango compiler instructions lack selected codegen flags")
    return dict(
        role="PRIVATE_INDEPENDENT_COLD_CODEGEN_TARGET_NOT_DELTA_ACCEPTANCE",
        native_executable_text_changed=True,
        before_sha256=sha(before),
        after_sha256=sha(after),
        before_text_sha256=sha(sections[0]),
        after_text_sha256=sha(sections[1]),
        before_text_bytes=len(sections[0]),
        after_text_bytes=len(sections[1]),
        compiler_flags=["/Od", "/Ob0", "/DNDEBUG"],
        compiler_instruction_files=commands,
        source_bytes_changed_between_builds=False,
        binary_cache="DISABLED",
        pe_bytes_manually_edited=False,
        native_delta_rollback_proven=False,
        phase3_complete=False,
        release_authorized=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-audit", "fresh-audit", "work", "recipe", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Disposable Windows CI native-target proof only")
    baseline = json.loads(args.baseline_audit.read_bytes())
    fresh = json.loads(args.fresh_audit.read_bytes())
    result = merge_audits(baseline, fresh)
    name = "pango-1.0-0.dll"
    original, target = (Path(a["dlls"][name]["loaded_path"]) for a in (baseline, fresh))
    if original.resolve() == target.resolve() or not target.resolve().is_relative_to(
        args.work.resolve()
    ):
        raise ValueError("Independent target native work directory required")
    before, after = original.read_bytes(), target.read_bytes()
    if (
        sha(before) != baseline["dlls"][name]["sha256"]
        or sha(after) != fresh["dlls"][name]["sha256"]
    ):
        raise ValueError("Audited native bytes changed before codegen comparison")
    files = list((args.work / "vcpkg/buildtrees/pango").rglob("build.ninja"))
    instructions = [(str(p.relative_to(args.work)), p.read_bytes()) for p in files]
    proof = codegen_evidence(before, after, instructions)
    # Execute the real freshly audited target function in this separate process.
    import ctypes

    with os.add_dll_directory(str(target.parent)):
        library = ctypes.CDLL(str(target))
        library.pango_version_string.argtypes = []
        library.pango_version_string.restype = ctypes.c_char_p
        version = library.pango_version_string().decode("ascii")
    if version != baseline["actual_pango_version_string"]:
        raise ValueError("Codegen target changed the noticed Pango implementation/version")
    proof["actual_pango_version_string"] = version
    recipe = args.recipe.read_bytes()
    proof["target_triplet_sha256"] = sha(recipe)
    proof["target_triplet"] = recipe.decode("utf-8-sig")
    proof["baseline_audit_sha256"] = sha(args.baseline_audit.read_bytes())
    proof["fresh_audit_sha256"] = sha(args.fresh_audit.read_bytes())
    result["private_codegen_variant"] = proof
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(
        "PASS: independently audited Source21 target; actual native .text differs, NOT delta acceptance"
    )


if __name__ == "__main__":
    main()

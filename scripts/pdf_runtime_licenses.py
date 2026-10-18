"""Prepare reviewable native-library notices; NEVER authorize distribution.

Original source verification is mandatory when collecting supplements. Replay
only checks the committed material for drift; it is not a new source audit.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
import zlib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / "docs/dependencies"
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
REQUIRED_GATES = {
    "COMPLETE_COMPONENT_LEGAL_REVIEW", "COMPILER_CRT_TERMS",
    "BUILD_SCRIPT_PERMISSIONS_AND_COMPLETENESS", "RECIPIENT_SOURCE_DELIVERY",
    "LGPL_SHARED_LIBRARY_REPLACEMENT", "PRODUCTION_BOOTSTRAP_UPDATES_AND_ACCEPTANCE",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_policy(inventory: dict, policy: dict) -> None:
    if (inventory["distribution_status"] != BLOCKED
            or inventory["source_archive"] != policy["source_archive"]
            or inventory["vcpkg_commit"] != policy["vcpkg_commit"]
            or policy["distribution_status"] != BLOCKED):
        raise ValueError("Pinned source or blocked distribution status changed")
    if set(inventory["source_packages"]) != set(policy["packages"]):
        raise ValueError("Package coverage changed; explicit review required")
    for name, item in inventory["source_packages"].items():
        selection = policy["packages"][name]
        if item["declared_port_license"] != selection["expected_declared_license"]:
            raise ValueError(f"License declaration changed: {name}")
        if not selection["selected_license"] or not selection["basis"]:
            raise ValueError(f"Missing explicit selection: {name}")
        if name != "pthread" and (not item["copyright_text_utf8_lossless"]
                or sha(item["copyright_text"].encode()) != item["copyright_sha256"]):
            raise ValueError(f"Invalid original copyright bytes: {name}")
    alias = inventory["source_packages"]["pthread"]
    if alias["selected_dlls"] or alias["delegated_license_packages"] != ["pthreads"]:
        raise ValueError("pthread is no longer a metadata-only alias")
    if {gate["id"] for gate in policy["open_gates"]} != REQUIRED_GATES:
        raise ValueError("Required distribution gates cannot be removed")
    for name, dll in inventory["dlls"].items():
        if name not in inventory["source_packages"][dll["source_package"]]["selected_dlls"]:
            raise ValueError("Uncovered native owner")
    fingerprint = sha(json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
    if fingerprint != policy["inventory_fingerprint_sha256"]:
        raise ValueError("Pinned inventory fingerprint changed")


def collect_materials(inventory: dict, policy: dict, archive: Path) -> dict:
    # Imports only on collection: replay needs the Python standard library only.
    from pdf_source_evidence import verify_sources

    validate_policy(inventory, policy)
    verified = verify_sources(inventory, archive)
    files = {}
    with zipfile.ZipFile(archive) as bundle:
        for key, required in policy["supplements"].items():
            matches = [n for n in bundle.namelist() if n.startswith(f"sources/{required['package']}/")
                       and "/".join(PurePosixPath(n).parts[3:]) == required["relative_path"]]
            if len(matches) != 1:
                raise ValueError(f"Supplement must resolve to exactly one source file: {key}")
            data = bundle.read(matches[0])
            if len(data) < required["minimum_bytes"]:
                raise ValueError(f"Incomplete license supplement: {key}")
            files[key] = {"archive_path": matches[0], "sha256": sha(data), "text": data.decode("utf-8")}
    result = {"schema": 1, "source_archive": inventory["source_archive"],
              "verified_source_materials": verified, "files": files}
    validate_materials(inventory, policy, result)
    return result


def validate_materials(inventory: dict, policy: dict, materials: dict) -> None:
    validate_policy(inventory, policy)
    if materials["source_archive"] != inventory["source_archive"] or set(materials["files"]) != set(policy["supplements"]):
        raise ValueError("Supplement archive/coverage mismatch")
    for key, item in materials["files"].items():
        required = policy["supplements"][key]
        parts = PurePosixPath(item["archive_path"]).parts
        if (len(parts) < 4 or parts[:2] != ("sources", required["package"])
                or "/".join(parts[3:]) != required["relative_path"]
                or ".." in parts):
            raise ValueError(f"Unexpected supplement source path: {key}")
        data = item["text"].encode("utf-8")
        if sha(data) != item["sha256"] or len(data) < required["minimum_bytes"]:
            raise ValueError(f"Supplement bytes mismatch: {key}")
        if not all(marker in item["text"] for marker in required["required_text"]):
            raise ValueError(f"Supplement lacks required license text: {key}")


def render(inventory: dict, policy: dict, materials: dict) -> tuple[str, dict]:
    validate_materials(inventory, policy, materials)
    sections = [
        "VIRA private PDF runtime — THIRD-PARTY NOTICES (review candidate)",
        "DO NOT DISTRIBUTE: " + BLOCKED,
        "These notices cover the captured native build, not all VIRA/Python/font dependencies. "
        "License selections are engineering proposals, NOT legal approval or a license grant for VIRA. "
        "Complete original texts, including unselected alternatives/tools, are preserved below. "
        "Their inclusion does not select a GPL alternative for the application.",
        "Portions of this software are copyright © 1996-2026 The FreeType Project "
        "(https://freetype.org). All rights reserved.",
        "Proposed LGPL route: LGPL-2.1 section 6(b), suitable shared-library mechanism. "
        "Recipients must be able to replace compatible LGPL DLLs and reverse engineer "
        "for debugging modifications. This route still needs actual packaged replacement "
        "tests and compatible application/EULA terms; dynamic DLLs alone do NOT prove compliance.",
        "Preferred corresponding source (not yet recipient-accessible): " + inventory["source_archive"]["sha256"],
    ]
    packages = {}
    for name, item in sorted(inventory["source_packages"].items()):
        choice = policy["packages"][name]
        packages[name] = {"declared_license": item["declared_port_license"],
                          "proposed_selected_license": choice["selected_license"],
                          "selected_dlls": item["selected_dlls"], "basis": choice["basis"],
                          "original_notice_sha256": item["copyright_sha256"]}
        sections.extend([f"===== {name} =====", "Proposed choice: " + choice["selected_license"],
                         choice["basis"], "Selected DLLs: " + (", ".join(item["selected_dlls"]) or "none; retained conservatively for build/header/static review"),
                         item["copyright_text"]])
    for key, item in sorted(materials["files"].items()):
        sections.extend([f"===== SOURCE SUPPLEMENT: {key} =====", item["archive_path"],
                         "SHA256: " + item["sha256"], item["text"]])
    text = "\n\n".join(sections) + "\n"
    review = {"schema": 1, "distribution_status": BLOCKED, "materials_status": "PREPARED_FOR_REVIEW_NOT_APPROVED",
              "source_archive": inventory["source_archive"], "notices_sha256": sha(text.encode()),
              "package_count": len(packages), "dll_count": len(inventory["dlls"]),
              "packages": packages, "supplement_sha256": {k: v["sha256"] for k, v in materials["files"].items()},
              "open_gates": policy["open_gates"]}
    return text, review


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def emit(materials: dict, group: int) -> None:
    if not 0 <= group < 8:
        raise ValueError("Invalid annotation group")
    payload = base64.b64encode(zlib.compress(json.dumps(materials, ensure_ascii=True).encode())).decode()
    chunks = [payload[i:i + 3000] for i in range(0, len(payload), 3000)]
    if len(chunks) > 64:
        raise ValueError("More annotation steps required; refusing truncated license evidence")
    for index in range(group * 8, min((group + 1) * 8, len(chunks))):
        record = json.dumps({"part": index, "total": len(chunks), "data": chunks[index]})
        print(f"::notice title=Verified native license materials::{record}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--emit-group", type=int)
    parser.add_argument("--out", type=Path, default=DEPS)
    args = parser.parse_args()
    inventory = json.loads((DEPS / "pdf-runtime-win64-source-inventory.json").read_text())
    policy = json.loads((DEPS / "pdf-runtime-license-policy.json").read_text())
    material_file = args.out / "pdf-runtime-license-materials.json"
    if args.emit_group is not None:
        emit(json.loads(material_file.read_text()), args.emit_group)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    materials = (collect_materials(inventory, policy, args.archive) if args.archive
                 else json.loads(material_file.read_text()))
    text, review = render(inventory, policy, materials)
    write_json(material_file, materials)
    (args.out / "pdf-runtime-THIRD-PARTY-NOTICES.txt").write_text(text, encoding="utf-8", newline="\n")
    write_json(args.out / "pdf-runtime-license-review.json", review)
    print(f"PASS: {len(review['packages'])} packages; notices prepared; {BLOCKED}")


if __name__ == "__main__":
    main()

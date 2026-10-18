"""Inspect private bundled-interpreter output from outside production site-packages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pdf_native_smoke import DIGITS, inspect_pdf
from pdf_runtime_inventory import BLOCKED


def verify(root: Path, reports: Path) -> dict:
    worker = json.loads((reports / "worker-proof.json").read_text())
    if not worker["isolated"] or not worker["development_dependencies_absent"] or not worker["ctypes_callbacks_verified"]:
        raise ValueError("Bundled interpreter isolation proof failed")
    if worker["distribution_status"] != BLOCKED:
        raise ValueError("Private candidate must not silently acquire distribution approval")
    inventory = json.loads((root / "native/pdf/runtime-inventory.json").read_text())
    expected_version = inventory.get("expected_pango_version_string")
    if expected_version is not None and (
        worker.get("pango_version_string") != expected_version
        or worker.get("expected_pango_version_string") != expected_version
        or inventory.get("private_consumption_only") is not True
        or inventory.get("modified_build_is_distribution_candidate") is not False
        or inventory.get("source_archive") is not None
    ):
        raise ValueError("Local-source consumer proof must match the executed modified Pango and remain private")
    for name, entry in inventory["dlls"].items():
        if hashlib.sha256((root / "native/pdf/bin" / name).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Candidate DLL changed: {name}")
    # The original production payload's manifest still applies to all its files.
    # Native candidate and Python caches were added privately after that manifest.
    manifest = json.loads((root / "install_manifest.json").read_text(encoding="utf-8-sig"))
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid payload manifest path")
        if "__pycache__" in relative.parts or relative.suffix == ".pyc":
            continue
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Original staged payload changed: {relative}")
    result = {"worker": worker, "dll_count": len(inventory["dlls"]), "documents": {}}
    for name, minimum in (("single-page", 1), ("multi-page", 2)):
        result["documents"][name] = inspect_pdf(
            (reports / f"{name}.pdf").read_bytes(), expected_digits=DIGITS, min_pages=minimum
        )
    if result["documents"]["single-page"]["pages"] != 1:
        raise ValueError("Short fixture must fit on one A4 page")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.app_root, args.reports)
    output = json.dumps(result, ensure_ascii=True)
    (args.reports / "bundled-proof.json").write_text(output, encoding="utf-8")
    print(output)
    summary = {"python": result["worker"]["python"], "version": result["worker"]["version"],
               "isolated": result["worker"]["isolated"], "dll_count": result["dll_count"],
               "loaded_dll_count": len(result["worker"]["loaded_dlls"]),
               "ctypes_callbacks_verified": result["worker"]["ctypes_callbacks_verified"],
               "distribution_status": BLOCKED, "documents": result["documents"],
               "pango_version_string": result["worker"].get("pango_version_string"),
               "expected_pango_version_string": result["worker"].get("expected_pango_version_string")}
    encoded = json.dumps(summary, ensure_ascii=True).replace("%", "%25")
    print(f"::notice title=Private bundled Python PDF proof::{encoded}")


if __name__ == "__main__":
    main()

"""Validate a verified delta ZIP before extracting it outside the installation."""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .update_engine import DeltaPlan, OpKind, VerificationError, verify_sha256

MAX_EXPANDED_BYTES = 512 * 1024 * 1024
INSTALL_ROOTS = {"app", "backend", "python", "scripts", "site-packages", "static", "tools"}
INSTALL_FILES = {"version.json", "install_manifest.json", "start_vira.cmd", "vira-updater.exe"}


def safe_relative(name: str) -> str:
    parts = name.rstrip("/").split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)}
    if not name or "\\" in name or ":" in name or "\x00" in name or any(
        p in ("", ".", "..") or p.endswith((".", " ")) or p.split(".")[0].upper() in reserved for p in parts
    ):
        raise VerificationError("unsafe delta path")
    return PurePosixPath(*parts).as_posix()


def _install_path(name: str) -> None:
    normalized = safe_relative(name)
    first = normalized.split("/", 1)[0]
    if first not in INSTALL_ROOTS and normalized not in INSTALL_FILES:
        raise VerificationError("delta targets a non-application path")


def extract_delta(archive: Path, destination: Path, base: str, target: str) -> None:
    """Called only AFTER archive SHA-256 verification. Fail before any extraction."""
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > 50_000 or sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES:
            raise VerificationError("delta expansion limit exceeded")
        names: set[str] = set()
        for info in infos:
            name = safe_relative(info.filename)
            folded = name.casefold()
            if folded in names or stat.S_ISLNK(info.external_attr >> 16):
                raise VerificationError("duplicate delta path or symbolic link")
            names.add(folded)
        required = {"update.json", "version.json", "install_manifest.json", "vira-updater.exe"}
        if not required.issubset(zf.namelist()):
            raise VerificationError("incomplete delta package")
        doc = json.loads(zf.read("update.json"))
        plan = DeltaPlan.from_json(doc)
        if plan.base_version != base or plan.target_version != target:
            raise VerificationError("delta base/target version mismatch")
        if json.loads(zf.read("version.json")).get("version") != target:
            raise VerificationError("delta version stamp mismatch")
        hashes = doc.get("hashes")
        if not isinstance(hashes, dict) or "vira-updater.exe" not in hashes:
            raise VerificationError("delta helper hash missing")
        for member, expected in hashes.items():
            safe_relative(member)
            verify_sha256(zf.read(member), str(expected))
        for op in plan.operations:
            _install_path(op.path)
            if op.op in (OpKind.ADD, OpKind.REPLACE):
                member = "files/" + op.path
                if member not in hashes:
                    raise VerificationError("delta file hash missing")
                verify_sha256(zf.read(member), op.sha256)
            elif op.op is OpKind.PATCH:
                safe_relative(op.patch)
                if not op.patch.startswith("patches/") or op.patch not in hashes:
                    raise VerificationError("delta patch hash missing")
        # destination is a fresh, private attempt directory, never {app} or data.
        destination.mkdir()
        for info in infos:
            path = destination / safe_relative(info.filename)
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(zf.read(info))

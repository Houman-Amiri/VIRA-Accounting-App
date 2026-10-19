"""Stdlib-only private PDF startup PREPARATION, never an installed entry point.

This module verifies a *plan*, not an activated runtime or legal permission.
No native loading, environment/sys.path mutation, mkdir, migration or app factory.
Only the separately pinned SDK is supported here; source21 requires its own future
binding. Historical Windows proofs do not prove this new preflight. Not MIT14.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SDK_SHA256 = "ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53"
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
REQUIRED = frozenset({
    "python/python.exe", "version.json", "private-utf8-process-manifest.json",
    "app/__init__.py", "app/private_pdf_bootstrap.py", "app/main.py",
    "app/services/pdf.py", "app/services/pdf_rendering.py", "app/services/pdf_fontconfig.py",
    "app/assets/fonts/Vazirmatn-Regular.ttf", "app/assets/fonts/Vazirmatn-Bold.ttf",
    "site-packages/cffi/__init__.py", "native/pdf/runtime-inventory.json",
})


def _digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Independent lower-case SHA256 required")
    return value


def _absolute(path: Path) -> None:
    if (not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts
            or path == Path(path.anchor)):
        raise ValueError("Non-root absolute path without traversal required")


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("Symlink/reparse-point paths are not supported")
        try:
            metadata = part.lstat()  # inspect the link itself, including broken junctions
        except FileNotFoundError:
            continue
        if getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ValueError("Symlink/reparse-point paths are not supported")


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("Non-finite JSON value")


def _read(path: Path, digest: str | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    if digest is not None and hashlib.sha256(raw).hexdigest() != _digest(digest):
        raise ValueError("Independent digest mismatch")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _member(root: Path, relative: object) -> Path:
    if not isinstance(relative, str):
        raise ValueError("Payload member must be a string")
    # Canonical POSIX names only; never normalize away an alias or escape.
    parts = relative.split("/")
    reserved = {"con", "prn", "aux", "nul", *[f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)]}
    if (not relative or "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute()
            or PureWindowsPath(relative).drive or any(
                p in ("", ".", "..") or p.endswith((".", " "))
                or p.split(".")[0].casefold() in reserved
                or any(c in p for c in '<>"|?*') or any(ord(c) < 32 for c in p)
                for p in parts)):
        raise ValueError("Unsafe or aliased payload member")
    candidate = root.joinpath(*parts)
    _no_links(candidate)
    if not candidate.is_file() or not candidate.resolve(strict=True).is_relative_to(root):
        raise ValueError("Payload member is absent or outside root")
    return candidate


@dataclass(frozen=True, slots=True)
class PrivateBootstrapPlan:
    """Explicit data only; digests come from the caller, never local recomputation."""

    payload_root: Path
    state_root: Path
    manifest_sha256: str
    inventory_sha256: str

    def __post_init__(self) -> None:
        _absolute(self.payload_root)
        _absolute(self.state_root)
        _digest(self.manifest_sha256)
        _digest(self.inventory_sha256)
        if (self.state_root.is_relative_to(self.payload_root)
                or self.payload_root.is_relative_to(self.state_root)):
            raise ValueError("Private state and payload must be disjoint")


@dataclass(frozen=True, slots=True)
class VerifiedPrivatePlan:
    """Immutable preflight snapshot, NOT a capability to skip future verification.

    Hashes are not signatures. A future activator must revalidate immediately
    before native loading; neither ACL/race safety nor activated ACP is proved.
    """

    plan: PrivateBootstrapPlan
    dlls: tuple[tuple[str, str], ...]
    preload: Path
    cache_root: Path
    payload_files: int
    scope: str = "PRIVATE_SDK_PREFLIGHT_ONLY_NO_NATIVE_ACTIVATION"


def verify_private_plan(plan: PrivateBootstrapPlan) -> VerifiedPrivatePlan:
    """Pure read-only validation, testable without Windows/third-party imports.

    This function alone does NOT enforce runtime entry order; prepare_private_plan
    adds those guards. No QA script, renderer hook or config factory is consumed.
    """
    if type(plan) is not PrivateBootstrapPlan:
        raise TypeError("Explicit PrivateBootstrapPlan required")
    root, state = plan.payload_root, plan.state_root
    _no_links(root)
    _no_links(state)
    root = root.resolve(strict=True)
    if not root.is_dir() or (state.exists() and not state.is_dir()):
        raise ValueError("Directory payload/state required")
    if state.exists() and any(state.iterdir()):
        raise ValueError("Only fresh empty private state is supported in this preparation")
    baseline = _read(_member(root, "install_manifest.json"), plan.manifest_sha256)
    entries = baseline.get("files")
    if not isinstance(entries, list):
        raise ValueError("Manifest files list required")
    paths: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("Manifest file object required")
        name = entry["path"]
        if name.casefold() in paths or name.casefold() == "install_manifest.json":
            raise ValueError("Duplicate/case-aliased or recursive manifest member")
        paths[name.casefold()] = name
        file = _member(root, name)
        if (type(entry.get("size")) is not int or entry["size"] < 0
                or file.stat().st_size != entry["size"] or _sha256(file) != _digest(entry.get("sha256"))):
            raise ValueError("Baseline file changed")
    if not set(paths.values()) >= REQUIRED:
        raise ValueError("Required application bootstrap members absent")
    actual = set()
    for file in root.rglob("*"):
        _no_links(file)
        if file.is_file() and file != root / "install_manifest.json":
            actual.add(file.relative_to(root).as_posix())
    if actual != set(paths.values()):
        raise ValueError("Payload has unmanifested files")
    if _sha256(root / "app/private_pdf_bootstrap.py") != _sha256(Path(__file__)):
        raise ValueError("Application preflight code differs from verified payload")
    if _read(root / "version.json").get("version") != "0.0.0-private-unicode-proof":
        raise ValueError("Private staged version required; no installed runtime activation")
    inventory = _read(root / "native/pdf/runtime-inventory.json", plan.inventory_sha256)
    dlls = inventory.get("dlls")
    upstream = inventory.get("upstream")
    if (inventory.get("origin") == "LOCAL_PINNED_VCPKG_SOURCE_BUILD"
            or not isinstance(upstream, dict) or upstream.get("sha256") != SDK_SHA256
            or inventory.get("distribution_status") != BLOCKED
            or not isinstance(dlls, dict) or len(dlls) != 27
            or inventory.get("preload_dlls", ["libffi-8.dll"]) != ["libffi-8.dll"]
            or "libffi-8.dll" not in dlls):
        raise ValueError("Only private pinned 27-DLL SDK supported; source21 is not accepted")
    verified = []
    names = set()
    for name, item in dlls.items():
        if (not isinstance(name, str) or "/" in name or "\\" in name
                or not name.casefold().endswith(".dll") or name.casefold() in names
                or not isinstance(item, dict)):
            raise ValueError("Invalid/case-aliased DLL inventory")
        names.add(name.casefold())
        file = _member(root, "native/pdf/bin/" + name)
        digest = _digest(item.get("sha256"))
        if _sha256(file) != digest:
            raise ValueError("DLL inventory hash mismatch")
        verified.append((name, digest))
    physical = {p.name for p in (root / "native/pdf/bin").iterdir() if p.name.casefold().endswith(".dll")}
    if physical != set(dlls):
        raise ValueError("Uninventoried native DLL present")
    pe = _read(root / "private-utf8-process-manifest.json")
    if (pe.get("private_only") is not True
            or pe.get("python_executable_is_unmodified_upstream_binary") is not False
            or pe.get("release_or_redistribution_approval") is not False
            or _digest(pe.get("executable_sha256_before")) == _digest(pe.get("executable_sha256_after"))
            or _sha256(root / "python/python.exe") != pe["executable_sha256_after"]):
        raise ValueError("Private modified interpreter receipt required, not activated ACP proof")
    return VerifiedPrivatePlan(plan, tuple(sorted(verified)), root / "native/pdf/bin/libffi-8.dll",
                               state / "pdf-cache", len(paths))


def prepare_private_plan(plan: PrivateBootstrapPlan) -> VerifiedPrivatePlan:
    """Guard a future private entry, but do not activate native code or create app."""
    if type(plan) is not PrivateBootstrapPlan:
        raise TypeError("Explicit PrivateBootstrapPlan required")
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Private Windows CI preparation only")
    if sys.version_info[:2] != (3, 11) or not all(
        getattr(sys.flags, name, 0) == 1 for name in ("isolated", "no_site", "dont_write_bytecode", "utf8_mode")
    ):
        raise RuntimeError("Bundled CPython 3.11 with -I -S -B -X utf8 required")
    allowed = {"app", __name__}
    sensitive = ("app", "cffi", "_cffi_backend", "ctypes", "_ctypes", "weasyprint", "uvicorn",
                 "sitecustomize", "usercustomize")
    if any(n not in allowed and any(n == p or n.startswith(p + ".") for p in sensitive) for n in sys.modules):
        raise RuntimeError("Sensitive import before application preflight")
    if (Path(sys.executable).resolve() != plan.payload_root / "python/python.exe"
            or Path(sys.base_prefix).resolve() != plan.payload_root / "python"
            or Path(__file__).resolve() != plan.payload_root / "app/private_pdf_bootstrap.py"):
        raise ValueError("Preflight and interpreter must belong to private payload")
    package = sys.modules.get("app")
    if package is not None and (
        Path(getattr(package, "__file__", "")).resolve() != plan.payload_root / "app/__init__.py"
        or tuple(Path(p).resolve() for p in getattr(package, "__path__", ())) != (plan.payload_root / "app",)
    ):
        raise ValueError("Foreign application package imported before preflight")
    runner = Path(os.environ["RUNNER_TEMP"])
    profile = Path(os.environ["LOCALAPPDATA"])
    for path in (runner, profile, plan.payload_root, plan.state_root, Path.cwd()):
        _absolute(path)
        _no_links(path)
    if (profile == runner or plan.payload_root == runner
            or not profile.is_relative_to(runner) or not plan.payload_root.is_relative_to(runner)
            or plan.state_root == profile or not plan.state_root.is_relative_to(profile)
            or not Path.cwd().is_relative_to(profile)
            or any(str(p).isascii() or " " not in str(p)
                   for p in (profile, plan.payload_root, plan.state_root, Path.cwd()))):
        raise ValueError("Runner-owned disjoint Unicode/spaced private paths required")
    return verify_private_plan(plan)

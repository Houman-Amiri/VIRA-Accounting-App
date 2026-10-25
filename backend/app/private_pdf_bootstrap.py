"""App-owned private PDF preflight and explicit SDK runtime, NOT installed startup.

verify/prepare remain read-only stdlib APIs. activate_private_sdk is an explicit
private Windows-CI context: reverify, pin native/UTF-8, keep loader lifetime, restore
process settings. No factory/QA imports/default opt-in; source mode requires its independent audit. Not MIT14.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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


SOURCE_ARCHIVE = "b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2"
SOURCE_MANIFEST = "784c8d196ad0da899e7d6b65d26aff4d4bf9bb00551526692cda9b47c43c2023"
SOURCE_FILE = "a530b81e21d8799996032c68398651ec802d62017bac88c6c9d3b7cebd89719a"
SOURCE_VERSION = "1.58.0-vira-local-source"


def validate_private_source_inventory(inventory: dict[str, Any], audit: dict[str, Any], digest: str) -> None:
    """App-owned audit continuity, NOT an independent compilation/signature proof."""
    if (inventory.get("origin") != "LOCAL_PINNED_VCPKG_SOURCE_BUILD"
            or inventory.get("private_consumption_only") is not True
            or inventory.get("modified_build_is_distribution_candidate") is not False
            or inventory.get("distribution_status") != BLOCKED
            or inventory.get("source_archive") is not None
            or inventory.get("binary_cache") != "DISABLED"
            or inventory.get("native_audit_sha256") != digest
            or inventory.get("expected_pango_version_string") != SOURCE_VERSION
            or inventory.get("preload_dlls") != ["ffi-8.dll"]):
        raise ValueError("Explicit private source inventory/audit binding required")
    if (audit.get("native_compilation") != "SUCCESS" or audit.get("local_preferred_source_replay") != "SUCCESS"
            or audit.get("distribution_status") != BLOCKED
            or audit.get("actual_pango_version_string") != SOURCE_VERSION
            or audit.get("application_present") is not False
            or audit.get("new_corresponding_source_archive_prepared") is not True
            or audit.get("original_archive_modified") is not False
            or audit.get("original_source_tree_count") != 19
            or audit.get("explicitly_modified_source_tree_count") != 1
            or audit.get("compiled_from_noticed_archive") is not True
            or audit.get("inline_change_date_notice_present_in_compiled_source") is not True
            or audit.get("input_source_trees_unchanged_during_compilation") is not True
            or audit.get("noticed_source_archive_sha256") != SOURCE_ARCHIVE
            or audit.get("noticed_source_file_sha256") != SOURCE_FILE
            or audit.get("noticed_source_kit_receipt", {}).get("modified_kit_manifest_sha256") != SOURCE_MANIFEST
            or audit.get("changed_packages") != ["pango"]
            or len(audit.get("preferred_source_trees", {})) != 20
            or len(inventory.get("dlls", {})) != 21 or audit.get("dll_count") != 21
            or set(inventory["dlls"]) != set(audit.get("dlls", {}))):
        raise ValueError("Exact noticed-source build witness required")
    for name, item in inventory["dlls"].items():
        actual = audit["dlls"][name]
        if item["sha256"] != actual["sha256"] or item["source_package"] != actual["source_package"]:
            raise ValueError("Source DLL hash/owner differs from audited build")
    if set(inventory.get("source_packages", {})) != set(audit["preferred_source_trees"]):
        raise ValueError("Source package set mismatch")
    for name, item in inventory["source_packages"].items():
        actual = audit["preferred_source_trees"][name]
        if item["patched_source_tree_sha256"] != actual["tree_sha256"] or item["patched_source_files"] != actual["source_entries"]:
            raise ValueError("Source tree differs from compiled audit")



@dataclass(frozen=True, slots=True)
class PrivateBootstrapPlan:
    """Explicit data only; digests come from the caller, never local recomputation."""

    payload_root: Path
    state_root: Path
    manifest_sha256: str
    inventory_sha256: str
    source_audit_sha256: str | None = None
    installed_anchor: Path | None = None
    installed_anchor_sha256: str | None = None

    def __post_init__(self) -> None:
        if (self.installed_anchor is None) != (self.installed_anchor_sha256 is None):
            raise ValueError("Paired independent installed anchor path/digest required")
        if self.installed_anchor is not None:
            _absolute(self.installed_anchor)
            _digest(self.installed_anchor_sha256)
            if self.source_audit_sha256 is None or self.installed_anchor.is_relative_to(self.payload_root):
                raise ValueError("External installed SOURCE anchor required")
        _absolute(self.payload_root)
        _absolute(self.state_root)
        _digest(self.manifest_sha256)
        _digest(self.inventory_sha256)
        if self.source_audit_sha256 is not None:
            _digest(self.source_audit_sha256)
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
    if plan.installed_anchor is None:
        if _read(root / "version.json").get("version") != "0.0.0-private-unicode-proof":
            raise ValueError("Private staged version required; no installed runtime activation")
    else:
        _no_links(plan.installed_anchor)
        # This app-owned parser is executed ONLY after the full independently
        # anchored manifest has verified every byte, including this module.
        parser = runpy.run_path(str(_member(root, "app/private_installed_source.py")))["anchor"]
        pin = parser(_read(plan.installed_anchor, plan.installed_anchor_sha256))
        if (pin["schema"] != 2 or pin["manifest_sha256"] != plan.manifest_sha256
                or pin["inventory_sha256"] != plan.inventory_sha256
                or pin["source_audit_sha256"] != plan.source_audit_sha256
                or pin["version"] != _read(root / "version.json").get("version")):
            raise ValueError("Independent installed version/manifest/native anchor differs")
    inventory = _read(root / "native/pdf/runtime-inventory.json", plan.inventory_sha256)
    dlls = inventory.get("dlls")
    source = plan.source_audit_sha256 is not None
    preload = "ffi-8.dll" if source else "libffi-8.dll"
    if source:
        audit = _read(_member(root, "native/pdf/source-audit.json"), plan.source_audit_sha256)
        assert plan.source_audit_sha256 is not None
        validate_private_source_inventory(inventory, audit, plan.source_audit_sha256)
    else:
        upstream = inventory.get("upstream")
        if (inventory.get("origin") == "LOCAL_PINNED_VCPKG_SOURCE_BUILD"
                or not isinstance(upstream, dict) or upstream.get("sha256") != SDK_SHA256
                or inventory.get("distribution_status") != BLOCKED
                or not isinstance(dlls, dict) or len(dlls) != 27
                or inventory.get("preload_dlls", ["libffi-8.dll"]) != ["libffi-8.dll"]
                or "libffi-8.dll" not in dlls):
            raise ValueError("Only private pinned 27-DLL SDK supported; source21 is not accepted")
    if not isinstance(dlls, dict):
        raise ValueError("Native DLL inventory object required")
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
    return VerifiedPrivatePlan(plan, tuple(sorted(verified)), root / "native/pdf/bin" / preload,
                               state / "pdf-cache", len(paths),
                               "PRIVATE_SOURCE_PREFLIGHT_ONLY_NO_NATIVE_ACTIVATION" if source
                               else "PRIVATE_SDK_PREFLIGHT_ONLY_NO_NATIVE_ACTIVATION")


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
    if plan.installed_anchor is not None:
        _no_links(plan.installed_anchor)
        if not plan.installed_anchor.is_relative_to(profile):
            raise ValueError("Installed anchor must belong to disposable private profile")
    return verify_private_plan(plan)


@dataclass(frozen=True, slots=True)
class PrivateSdkActivation:
    """Plain diagnostics only; native objects/handles never escape the context."""

    pid: int
    windows_acp: int
    libffi: str
    manifest_sha256: str
    inventory_sha256: str
    payload_files: int
    dll_count: int
    bootstrap_temp: str
    role: str = "APP_OWNED_PRIVATE_SDK_ACTIVATION_NOT_INSTALLED"
    source_audit_sha256: str | None = None


@contextmanager
def activate_private_sdk(plan: PrivateBootstrapPlan) -> Iterator[PrivateSdkActivation]:
    """SDK-only opt-in; never infer source mode or accept a cached snapshot."""
    if type(plan) is not PrivateBootstrapPlan:
        raise TypeError("Explicit PrivateBootstrapPlan required")
    if plan.source_audit_sha256 is not None:
        raise ValueError("Source plan requires explicit activate_private_source")
    with _activate_private(plan) as active:
        yield active


@contextmanager
def activate_private_source(plan: PrivateBootstrapPlan) -> Iterator[PrivateSdkActivation]:
    """Separate source-only opt-in, exact noticed-build audit required."""
    if type(plan) is not PrivateBootstrapPlan:
        raise TypeError("Explicit PrivateBootstrapPlan required")
    if plan.source_audit_sha256 is None:
        raise ValueError("Independent source audit digest required")
    with _activate_private(plan) as active:
        yield active


@contextmanager
def _activate_private(plan: PrivateBootstrapPlan) -> Iterator[PrivateSdkActivation]:
    """Explicit one-process SDK activation, never accept a cached verification.

    Hold the absolute CFFI preload and DLL-directory handle for the entire body.
    Restore env/path/TEMP on every exit, not module imports or OS-loaded libraries:
    another activation requires a fresh process. No settings/QA/config callbacks.
    A separate fresh bootstrap workspace is required, not a persistent business DB.
    """
    verified = prepare_private_plan(plan)
    # No cached snapshot can bypass the complete check at the loading boundary.
    verified = verify_private_plan(plan)
    root, state = plan.payload_root, plan.state_root
    names = ("PATH", "WEASYPRINT_DLL_DIRECTORIES", "TEMP", "TMP", "FONTCONFIG_FILE", "FONTCONFIG_PATH")
    previous = {name: os.environ.get(name) for name in names}
    old_path, old_temp = sys.path[:], tempfile.tempdir
    created_state = not state.exists()
    handle = None
    try:
        state.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="bootstrap-", dir=state) as directory:
            os.environ["TEMP"] = os.environ["TMP"] = directory
            tempfile.tempdir = None
            if Path(tempfile.gettempdir()).resolve() != Path(directory).resolve():
                raise ValueError("Private bootstrap TEMP escaped workspace")
            native = root / "native/pdf/bin"
            os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(native)
            os.environ["PATH"] = str(native) + os.pathsep + (previous["PATH"] or "")
            sys.path[:0] = [str(root / "site-packages"), str(root)]
            handle = os.add_dll_directory(str(native))  # type: ignore[attr-defined]
            # First third-party import, absolute preload BEFORE ctypes/app/WeasyPrint.
            from cffi import FFI

            pinned = FFI().dlopen(str(verified.preload), flags=0x1000)
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
            kernel.GetACP.restype = ctypes.c_uint
            if kernel.GetACP() != 65001:
                raise ValueError("Private SDK process ACP must be 65001")
            kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel.GetModuleHandleW.restype = wintypes.HMODULE
            kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
            kernel.GetModuleFileNameW.restype = wintypes.DWORD
            loaded_preload = None
            for name, _ in verified.dlls:
                module = kernel.GetModuleHandleW(name)
                if not module:
                    if name == verified.preload.name:
                        raise ValueError("Private SDK preload not mapped")
                    continue
                buffer = ctypes.create_unicode_buffer(32768)
                if not kernel.GetModuleFileNameW(module, buffer, len(buffer)):
                    raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
                if Path(buffer.value).resolve() != native / name:
                    raise ValueError("Foreign native module before app entry")
                if name == verified.preload.name:
                    loaded_preload = buffer.value
            if loaded_preload is None or pinned is None:
                raise RuntimeError("Private native preload lifetime failure")
            # Source21 shutdown receipts audit the entire loaded closure, including
            # when this process has never rendered a PDF. Do not depend on lazy
            # renderer imports to map all audited DLLs. Keep absolute handles alive
            # throughout the app body; reject foreign dependency resolution too.
            source_handles = []
            if plan.source_audit_sha256 is not None:
                for name, _ in verified.dlls:
                    source_handles.append(ctypes.CDLL(str(native / name)))
                for name, _ in verified.dlls:
                    module = kernel.GetModuleHandleW(name)
                    buffer = ctypes.create_unicode_buffer(32768)
                    if not module or not kernel.GetModuleFileNameW(module, buffer, len(buffer)):
                        raise RuntimeError("Private source closure not mapped")
                    if Path(buffer.value).resolve() != native / name:
                        raise ValueError("Foreign source module before app entry")
            yield PrivateSdkActivation(os.getpid(), kernel.GetACP(), loaded_preload,
                                       plan.manifest_sha256, plan.inventory_sha256,
                                       verified.payload_files, len(verified.dlls), directory,
                                       "APP_OWNED_PRIVATE_SOURCE_ACTIVATION_NOT_INSTALLED"
                                       if plan.source_audit_sha256 else "APP_OWNED_PRIVATE_SDK_ACTIVATION_NOT_INSTALLED",
                                       plan.source_audit_sha256)
            if any(Path(directory).iterdir()):
                raise ValueError("Private bootstrap temporary files leaked")
            if pinned is None or (
                plan.source_audit_sha256 is not None and len(source_handles) != len(verified.dlls)
            ):
                raise RuntimeError("Private native preload lost during application body")
    finally:
        try:
            if handle is not None:
                handle.close()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            sys.path[:], tempfile.tempdir = old_path, old_temp
            if created_state and state.exists():
                _no_links(state)
                state.rmdir()  # only this newly-created leaf; never recursive user-state deletion

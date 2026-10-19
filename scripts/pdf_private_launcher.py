"""Private CI-only pre-import launcher; NOT the installed application launcher.

Standard library until payload verification completes. This phase supports ONLY
stock-SDK preflight, not a new source-build claim. No installer, HTTP service,
release authorization, site customization, shell evaluation or WeasyPrint patch.
Outside the explicitly scoped native-build MIT grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

SDK_SHA256 = "ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53"
BLOCKED = "BLOCKED_PENDING_LICENSE_AND_CORRESPONDING_SOURCE_REVIEW"
SENSITIVE = ("app", "cffi", "_cffi_backend", "ctypes", "_ctypes", "weasyprint", "uvicorn",
             "sitecustomize", "usercustomize")
REQUIRED = {
    "python/python.exe", "scripts/pdf_private_launcher.py", "scripts/pdf_unicode_probe.py",
    "app/services/pdf.py", "app/services/pdf_fontconfig.py", "site-packages/cffi/__init__.py",
    "private-utf8-process-manifest.json", "native/pdf/runtime-inventory.json", "version.json",
}


def startup_guards(platform: str, flags: object, modules: object) -> None:
    if platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Private isolated Windows CI only")
    if not all(getattr(flags, name, 0) == 1 for name in ("isolated", "no_site", "dont_write_bytecode", "utf8_mode")):
        raise RuntimeError("Private launcher requires -I -S -B -X utf8")
    if any(name == p or name.startswith(p + ".") for name in modules for p in SENSITIVE):
        raise RuntimeError("Sensitive module imported before private bootstrap")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path, expected: str | None = None) -> dict:
    raw = path.read_bytes()
    if expected is not None and (re.fullmatch(r"[0-9a-f]{64}", expected) is None
                                 or hashlib.sha256(raw).hexdigest() != expected):
        raise ValueError(f"Independent digest mismatch: {path.name}")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def member(root: Path, relative: str) -> Path:
    """Reject Windows and POSIX escapes, including on the Linux test host."""
    normalized = relative.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (not normalized or path.is_absolute() or PureWindowsPath(relative).drive
            or ":" in normalized or any(p in ("", ".", "..") for p in normalized.split("/"))):
        raise ValueError("Unsafe payload member")
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("Payload member escaped its root or is not a file")
    return resolved


def validate_payload(root: Path, manifest_digest: str, inventory_digest: str) -> dict:
    baseline = read_json(root / "install_manifest.json", manifest_digest)
    paths = set()
    for entry in baseline["files"]:
        relative = entry["path"]
        # Windows paths are case insensitive. No ambiguous/case-aliased entries.
        key = relative.replace("\\", "/").casefold()
        if key in paths:
            raise ValueError("Duplicate payload member")
        paths.add(key)
        file = member(root, relative)
        if file.stat().st_size != entry["size"] or sha256(file) != entry["sha256"]:
            raise ValueError(f"Baseline file changed: {relative}")
    if not paths >= REQUIRED:
        raise ValueError("Required bootstrap files absent from baseline")
    if read_json(root / "version.json")["version"] != "0.0.0-private-unicode-proof":
        raise ValueError("Not a private staged payload")
    inventory = read_json(root / "native/pdf/runtime-inventory.json", inventory_digest)
    if (inventory.get("upstream", {}).get("sha256") != SDK_SHA256
            or inventory.get("distribution_status") != BLOCKED
            or inventory.get("origin") == "LOCAL_PINNED_VCPKG_SOURCE_BUILD"
            or len(inventory["dlls"]) != 27):
        raise ValueError("Only separately pinned 27-DLL stock SDK preflight is supported")
    for name, entry in inventory["dlls"].items():
        if "/" in name or "\\" in name or not name.lower().endswith(".dll"):
            raise ValueError("Invalid native basename")
        relative = "native/pdf/bin/" + name
        if relative.casefold() not in paths or sha256(member(root, relative)) != entry["sha256"]:
            raise ValueError("Native inventory/baseline mismatch")
    if inventory.get("preload_dlls", ["libffi-8.dll"]) != ["libffi-8.dll"] or "libffi-8.dll" not in inventory["dlls"]:
        raise ValueError("Unreviewed preload policy")
    pe = read_json(root / "private-utf8-process-manifest.json")
    if (pe.get("private_only") is not True
            or pe.get("python_executable_is_unmodified_upstream_binary") is not False
            or pe.get("release_or_redistribution_approval") is not False
            or pe["executable_sha256_before"] == pe["executable_sha256_after"]
            or sha256(root / "python/python.exe") != pe["executable_sha256_after"]):
        raise ValueError("Private modified executable provenance mismatch")
    return inventory


def main() -> None:
    startup_guards(sys.platform, sys.flags, sys.modules)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("app-root", "contexts", "state-root", "out-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--payload-manifest-sha256", required=True)
    parser.add_argument("--reuse-state", action="store_true")
    args = parser.parse_args()
    root = args.app_root.resolve(strict=True)
    runner = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    if not root.is_relative_to(runner) or root == runner:
        raise ValueError("Private payload must be below runner TEMP")
    if (sys.version_info[:2] != (3, 11) or Path(sys.executable).resolve() != root / "python/python.exe"
            or Path(sys.base_prefix).resolve() != root / "python"):
        raise ValueError("Only the private bundled CPython 3.11 may launch")
    inventory = validate_payload(root, args.payload_manifest_sha256, args.inventory_sha256)
    profile = Path(os.environ["LOCALAPPDATA"]).resolve(strict=True)
    state = args.state_root.resolve()
    if (not profile.is_relative_to(runner) or profile == runner or not state.is_relative_to(profile)
            or any(str(p).isascii() or " " not in str(p) for p in (root, profile, state, Path.cwd()))):
        raise ValueError("Isolated Unicode/spaced profile, state, app and CWD required")
    bootstrap_temp = profile / "پوشه موقت راه‌انداز"
    bootstrap_temp.mkdir(exist_ok=True)
    native = root / "native/pdf/bin"
    names = ("PATH", "WEASYPRINT_DLL_DIRECTORIES", "TEMP", "TMP", "FONTCONFIG_FILE", "FONTCONFIG_PATH")
    previous = {name: os.environ.get(name) for name in names}
    old_path, old_argv, old_temp = sys.path[:], sys.argv[:], tempfile.tempdir
    handle = None
    try:
        os.environ["TEMP"] = os.environ["TMP"] = str(bootstrap_temp)
        tempfile.tempdir = None
        if Path(tempfile.gettempdir()).resolve() != bootstrap_temp:
            raise ValueError("Bootstrap TEMP escaped private Unicode profile")
        os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(native)
        os.environ["PATH"] = str(native) + os.pathsep + (previous["PATH"] or "")
        sys.path[:0] = [str(root / "site-packages"), str(root)]
        handle = os.add_dll_directory(str(native))
        # FIRST third-party import: never ctypes/app/WeasyPrint before this pin.
        from cffi import FFI

        pinned = FFI().dlopen(str(native / "libffi-8.dll"), flags=0x1000)
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetACP.restype = ctypes.c_uint
        if kernel.GetACP() != 65001:
            raise ValueError("Private process manifest did not activate ACP 65001")
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        kernel.GetModuleFileNameW.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        module = kernel.GetModuleHandleW("libffi-8.dll")
        if not module or not kernel.GetModuleFileNameW(module, buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
        if Path(buffer.value).resolve() != native / "libffi-8.dll":
            raise ValueError("Foreign libffi loaded before application entry")
        pre_entry = {"schema": 1, "role": "PRIVATE_STOCK_SDK_LAUNCHER_NOT_SOURCE_BUILD",
                     "pid": os.getpid(), "no_site": sys.flags.no_site, "isolated": sys.flags.isolated,
                     "utf8_mode": sys.flags.utf8_mode, "windows_acp": kernel.GetACP(),
                     "app_and_weasyprint_absent_before_entry": not any(n == p or n.startswith(p + ".") for n in sys.modules for p in ("app", "weasyprint", "uvicorn")),
                     "inventory_sha256": args.inventory_sha256, "payload_manifest_sha256": args.payload_manifest_sha256,
                     "bootstrap_temp": str(bootstrap_temp), "libffi": buffer.value, "dll_count": len(inventory["dlls"]),
                     "release_authorized": False, "ordinary_launcher_changed": False,
                     "new_source_build_proven": False}
        if not pre_entry["app_and_weasyprint_absent_before_entry"]:
            raise ValueError("Application imported during bootstrap")
        target = member(root, "scripts/pdf_unicode_probe.py")
        sys.argv = [str(target), "--app-root", str(root), "--contexts", str(args.contexts),
                    "--state-root", str(state), "--out-dir", str(args.out_dir)]
        if args.reuse_state:
            sys.argv.append("--reuse-state")
        runpy.run_path(str(target), run_name="__main__")
        if pinned is None:  # keep native preload alive until target/cleanup finish
            raise RuntimeError("Preload lifetime failure")
        if any(bootstrap_temp.iterdir()):
            raise ValueError("Bootstrap temporary files leaked")
        pre_entry["target_completed"] = True
        (args.out_dir / "launcher-proof.json").write_text(json.dumps(pre_entry, indent=2) + "\n", encoding="utf-8")
        print("::notice title=Private pre-import launcher proof::" + json.dumps(pre_entry), flush=True)
    finally:
        if handle is not None:
            handle.close()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        sys.path[:], sys.argv[:], tempfile.tempdir = old_path, old_argv, old_temp


if __name__ == "__main__":
    main()

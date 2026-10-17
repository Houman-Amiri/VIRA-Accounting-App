"""Standard-library-only worker for the private bundled-CPython PDF proof.

Run with the staged python.exe -I. This does not install a runtime on a user's PC.
"""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import sys
from pathlib import Path


def main() -> None:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Private isolated Windows CI runner required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.app_root.resolve()
    native = root / "native/pdf/bin"
    if sys.version_info[:2] != (3, 11) or Path(sys.executable).resolve().parent != root / "python":
        raise ValueError("The staged CPython 3.11 interpreter must execute the probe")
    if Path(sys.base_prefix).resolve() != root / "python":
        raise ValueError("Interpreter is using a foreign base prefix")
    sys.path[:0] = [str(root / "site-packages"), str(root)]
    if any(".venv" in Path(p).parts for p in sys.path if p):
        raise ValueError("Development environment leaked into staged interpreter")
    for name in ("pypdf", "pefile"):
        if importlib.util.find_spec(name) is not None:
            raise ValueError(f"Development-only dependency leaked into production: {name}")
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(native)
    os.environ["FONTCONFIG_FILE"] = str(root / "native/pdf/fonts.conf")
    os.environ["FONTCONFIG_PATH"] = str(root / "native/pdf")
    handle = os.add_dll_directory(str(native))
    try:
        from app.services.pdf import render_pdf

        contexts = json.loads(args.contexts.read_text(encoding="utf-8-sig"))
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, context in contexts.items():
            if name not in ("single-page", "multi-page"):
                raise ValueError("Unknown synthetic fixture")
            data = render_pdf("proforma.html", context)
            if not data.startswith(b"%PDF-"):
                raise ValueError("HTML fallback is not a bundled native PDF proof")
            (args.out_dir / f"{name}.pdf").write_bytes(data)
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        kernel.GetModuleFileNameW.restype = wintypes.DWORD
        inventory = json.loads((native.parent / "runtime-inventory.json").read_text())
        loaded = {}
        for name in inventory["dlls"]:
            module = kernel.GetModuleHandleW(name)
            if not module:
                continue  # delay imports are included conservatively, not necessarily loaded
            buffer = ctypes.create_unicode_buffer(32768)
            if not kernel.GetModuleFileNameW(module, buffer, len(buffer)):
                raise ctypes.WinError(ctypes.get_last_error())
            path = Path(buffer.value).resolve()
            if path.parent != native:
                raise ValueError(f"Foreign native dependency loaded: {path}")
            loaded[name] = str(path)
        if not set(inventory["roots"]) <= loaded.keys():
            raise ValueError("Every core native dependency must actually load from the candidate")
        result = {
            "python": str(Path(sys.executable).resolve()), "base_prefix": sys.base_prefix,
            "version": sys.version, "isolated": sys.flags.isolated,
            "development_dependencies_absent": True, "loaded_dlls": loaded,
            "distribution_status": inventory["distribution_status"],
        }
        (args.out_dir / "worker-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    finally:
        handle.close()


if __name__ == "__main__":
    main()

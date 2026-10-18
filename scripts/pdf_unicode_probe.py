"""Private Unicode bootstrap worker, NOT a production/release entry point.

Run with the staged python.exe -I. This does not install a runtime on a user's PC.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import locale
import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Private isolated Windows CI runner required")
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--reuse-state", action="store_true")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-pango-version")
    args = parser.parse_args()
    if sys.flags.utf8_mode != 1 or locale.getpreferredencoding(False).lower().replace('_', '-') != 'utf-8':
        raise ValueError("Unicode native paths require explicit CPython -X utf8, not a locale-dependent codec")
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
    inventory = json.loads((native.parent / "runtime-inventory.json").read_text())
    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(native)
    os.environ["PATH"] = str(native) + os.pathsep + os.environ.get("PATH", "")
    state = args.state_root.resolve()
    cache = state / "حافظه قلم با فاصله"
    temp = state / "پوشه موقت با فاصله"
    for path in (root, state, cache, temp):
        if str(path).isascii() or " " not in str(path):
            raise ValueError("App, state, cache and TEMP must all contain Unicode and spaces")
    cache.mkdir(parents=True, exist_ok=args.reuse_state)
    temp.mkdir(parents=True, exist_ok=args.reuse_state)
    profile = Path(os.environ["LOCALAPPDATA"]).resolve()
    if str(profile).isascii() or " " not in str(profile) or not state.is_relative_to(profile):
        raise ValueError("State must be inside the private Unicode LOCALAPPDATA")
    if any(temp.iterdir()):
        raise ValueError("A new/restarted worker must not inherit temporary font files")
    os.environ["TEMP"] = os.environ["TMP"] = str(temp)
    tempfile.tempdir = None
    if Path(tempfile.gettempdir()).resolve() != temp:
        raise ValueError("Private worker did not select Unicode TEMP")
    # Deliberately unusable legacy getenv path: active document config must not
    # depend on the former ASCII fonts.conf workaround or system configuration.
    config = state / "تنظیم ناموجود fonts.conf"
    assert not config.exists()
    os.environ["FONTCONFIG_FILE"] = str(config)
    os.environ["FONTCONFIG_PATH"] = str(state)
    handle = os.add_dll_directory(str(native))
    try:
        # CPython's _ctypes and GLib both import libffi-8.dll. Pin the audited
        # candidate BEFORE ctypes/WeasyPrint imports; never silently borrow the
        # interpreter's different DLL with the same basename.
        from cffi import FFI

        ffi = FFI()
        preloads = inventory.get("preload_dlls", ["libffi-8.dll"])
        if not preloads or any(name not in inventory["dlls"] for name in preloads):
            raise ValueError("Preload must belong to the audited dependency closure")
        pinned_libffi = [ffi.dlopen(name, flags=0x1000) for name in preloads]
        import ctypes

        integer_callback = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(lambda n: n + 1)
        float_callback = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_double)(lambda n: n + 0.5)
        if integer_callback(41) != 42 or float_callback(41.5) != 42.0:
            raise ValueError("Audited libffi is incompatible with ctypes callbacks")
        if pinned_libffi is None:
            raise ValueError("Native libffi preload failed")
        from app.services.pdf import render_pdf
        from app.services.pdf_fontconfig import configuration_xml, private_font_configuration

        xml = configuration_xml(cache)
        (state / "memory-fontconfig.xml").write_bytes(xml)
        documents = {}

        contexts = json.loads(args.contexts.read_text(encoding="utf-8-sig"))
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for name, context in contexts.items():
            if name not in ("single-page", "multi-page"):
                raise ValueError("Unknown synthetic fixture")
            with private_font_configuration(cache) as font_config:
                data = render_pdf("proforma.html", context, font_configuration=font_config)
                folder = Path(font_config._folder)
                if folder.parent.resolve() != temp or str(folder).isascii():
                    raise ValueError("WeasyPrint font files escaped Unicode TEMP")
                actual = {hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
                expected = {hashlib.sha256((root / 'app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular','Bold')}
                if actual != expected:
                    raise ValueError("Temporary fonts must be exactly the two bundled Vazirmatn files")
                from weasyprint.text import fonts
                if fonts.PREFERRED_ENCODING.lower().replace('_','-') != 'utf-8':
                    raise ValueError("WeasyPrint native font path encoding must be UTF-8")
                if fonts.fontconfig.FcConfigGetFonts(font_config._config, fonts.fontconfig.FcSetSystem).nfont != 0:
                    raise ValueError("System fonts leaked into private configuration")
                documents[name] = {"font_folder": str(folder), "font_sha256": sorted(actual), "system_fonts": 0}
            if folder.exists():
                raise ValueError("Temporary font directory leaked after document cleanup")
            documents[name]['font_temp_cleaned'] = True
            if not data.startswith(b"%PDF-"):
                raise ValueError("HTML fallback is not a bundled native PDF proof")
            (args.out_dir / f"{name}.pdf").write_bytes(data)
        pango_names = [name for name in inventory["dlls"] if name in ("pango-1.0-0.dll", "libpango-1.0-0.dll")]
        if len(pango_names) != 1:
            raise ValueError("Exactly one audited Pango implementation required")
        pango = ctypes.CDLL(str(native / pango_names[0]))
        pango.pango_version_string.argtypes = []
        pango.pango_version_string.restype = ctypes.c_char_p
        actual_pango_version = pango.pango_version_string().decode("ascii")
        if args.expected_pango_version is not None and actual_pango_version != args.expected_pango_version:
            raise ValueError(f"Rendered payload did not consume the modified Pango: {actual_pango_version}")
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        kernel.GetModuleFileNameW.restype = wintypes.DWORD
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
            "utf8_mode": sys.flags.utf8_mode, "preferred_encoding": locale.getpreferredencoding(False),
            "weasyprint_path_encoding": fonts.PREFERRED_ENCODING,
            "development_dependencies_absent": True, "ctypes_callbacks_verified": True,
            "fontconfig_file": None, "legacy_fontconfig_env_ignored": str(config),
            "fontconfig_mode": "EXPLICIT_UTF8_MEMORY_NO_SYSTEM_FONTS",
            "fontconfig_xml_sha256": hashlib.sha256(xml).hexdigest(),
            "unicode_temp": str(temp), "unicode_state": str(state),
            "localappdata": str(profile), "working_directory": str(Path.cwd()),
            "reused_state": args.reuse_state,
            "font_documents": documents, "loaded_dlls": loaded,
            "pango_version_string": actual_pango_version,
            "expected_pango_version_string": args.expected_pango_version,
            "distribution_status": inventory["distribution_status"],
        }
        (args.out_dir / "worker-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    finally:
        handle.close()


if __name__ == "__main__":
    main()

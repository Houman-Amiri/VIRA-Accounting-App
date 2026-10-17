"""Strict native PDF proof, not an installed-client or financial acceptance test.

Only synthetic documents are written. No database, server, release, or user data.
The inspection dependencies are development-only, never production requirements.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import os
import re
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from pypdf import PdfReader

DIGITS = "0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
NATIVE_DLLS = (
    "libgobject-2.0-0.dll", "libpango-1.0-0.dll", "libharfbuzz-0.dll",
    "libfontconfig-1.dll", "libpangoft2-1.0-0.dll",
)


def inspect_pdf(data: bytes, *, expected_digits: str = "", min_pages: int = 1) -> dict:
    """Reject HTML, unembedded/substitute fonts, wrong paper, and missing digits.

    Inspect actual page text operators and embedded TTFs, not CSS family names or
    just a PDF header. ToUnicode maps only glyph codes
    actually referenced by page text operators; unused map entries do not count.
    """
    if not data.startswith(b"%PDF-"):
        raise ValueError("Native PDF required; HTML fallback is not evidence")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted or len(reader.pages) < min_pages:
        raise ValueError("Unencrypted PDF with the required page count expected")
    fonts: dict[str, dict] = {}
    for page in reader.pages:
        if abs(float(page.mediabox.width) - 595.28) > 1 or abs(float(page.mediabox.height) - 841.89) > 1:
            raise ValueError("A4 portrait page expected")
        contents = page.get_contents()
        if contents is None:
            raise ValueError("Empty PDF page")
        current = None
        used: dict[str, set[int]] = {}
        for operands, operator in contents.operations:
            if operator == b"Tf":
                current = operands[0]
            elif operator in (b"Tj", b"TJ", b"'", b'"'):
                tokens = operands[0] if operator == b"TJ" else operands[-1:]
                for token in tokens:
                    if not isinstance(token, (str, bytes)) or not token:
                        continue
                    if current is None:
                        raise ValueError("Text without an active font")
                    raw = token if isinstance(token, bytes) else token.original_bytes
                    if len(raw) % 2:
                        raise ValueError("Expected two-byte Identity-H glyph codes")
                    used.setdefault(current, set()).update(
                        int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw), 2)
                    )
        if not used:
            raise ValueError("No identifiable text fonts used on page")
        for name in used:
            font = page["/Resources"]["/Font"][name].get_object()
            base_name = str(font.get("/BaseFont", ""))
            if font.get("/Encoding") != "/Identity-H":
                raise ValueError("Expected Identity-H text encoding")
            descendants = font.get("/DescendantFonts")
            actual = descendants[0].get_object() if descendants else font
            descriptor = actual.get("/FontDescriptor")
            if descriptor is None:
                raise ValueError(f"Unembedded font: {base_name}")
            descriptor = descriptor.get_object()
            stream = descriptor.get("/FontFile2")
            if stream is None:
                raise ValueError(f"Embedded TrueType font required: {base_name}")
            with TTFont(io.BytesIO(stream.get_object().get_data())) as embedded:
                family = embedded["name"].getDebugName(1) or ""
                weight = embedded["OS/2"].usWeightClass
                if "Vazirmatn" not in family or weight not in (400, 700):
                    raise ValueError(f"Non-Vazirmatn text/numeric font: {family!r}, {weight}")
                if embedded["maxp"].numGlyphs < 2:
                    raise ValueError("Empty embedded font")
            if "Vazirmatn" not in base_name or "/ToUnicode" not in font:
                raise ValueError(f"Missing named font/Unicode map: {base_name}")
            cmap = font["/ToUnicode"].get_data().decode("ascii")
            mapping = {}
            for block in re.findall(r"beginbfchar(.*?)endbfchar", cmap, re.S):
                for cid, encoded in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", block):
                    mapping[int(cid, 16)] = bytes.fromhex(encoded).decode("utf-16-be")
            if used[name] - mapping.keys():
                raise ValueError(f"Missing Unicode mapping for used glyphs: {base_name}")
            characters = set("".join(mapping[cid] for cid in used[name]))
            if not characters:
                raise ValueError(f"No supported Unicode glyph mapping: {base_name}")
            entry = fonts.setdefault(base_name, {"weight": weight, "characters": set()})
            entry["characters"].update(characters)
    if {f["weight"] for f in fonts.values()} != {400, 700}:
        raise ValueError("Both Regular and Bold must be embedded and used")
    for weight in (400, 700):
        available = set().union(*(f["characters"] for f in fonts.values() if f["weight"] == weight))
        missing = set(expected_digits) - available
        if missing:
            raise ValueError(f"Digits missing from weight {weight}: {sorted(missing)}")
    return {
        "pages": len(reader.pages), "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data), "fonts": [
            {"name": name, "weight": font["weight"],
             "digits": "".join(c for c in DIGITS if c in font["characters"])}
            for name, font in sorted(fonts.items())
        ],
    }


def loaded_native_paths() -> dict[str, str]:
    """Windows proof must use the explicit fixture, not preinstalled MSYS/GTK."""
    if sys.platform != "win32":
        return {}
    from ctypes import wintypes

    fixture = Path(os.environ["WEASYPRINT_DLL_DIRECTORIES"]).resolve()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetModuleFileNameW.restype = wintypes.DWORD
    paths = {}
    for name in NATIVE_DLLS:
        handle = kernel.GetModuleHandleW(name)
        path = ctypes.create_unicode_buffer(32768)
        if not handle or not kernel.GetModuleFileNameW(handle, path, len(path)):
            raise ValueError(f"Native dependency was not loaded: {name}")
        resolved = Path(path.value).resolve()
        if resolved.parent != fixture:
            raise ValueError(f"System/foreign native dependency used: {resolved}")
        paths[name] = str(resolved)
    return paths


def fixture_context(lines: int) -> dict:
    # Deliberate glyph probes, NOT financial values or a numerical acceptance.
    probe = "0123456789 / ۰۱۲۳۴۵۶۷۸۹ / ٠١٢٣٤٥٦٧٨٩"
    return {
        "company": {"name": "V.I.R.A", "tagline": "آزمون بومی — " + probe},
        "order": {
            "order_number": "۱۲۳۴۵۶۷۸۹۰", "order_date": "2026-10-17",
            "order_date_jalali": "۱۴۰۵/۰۷/۲۵",
            "customer": {"name": "مشتری آزمایشی <script>alert(1)</script>",
                         "phone": "۰۹۱۲۳۴۵۶۷۸۹", "address": "تهران — دادهٔ ساختگی"},
            "lines": [{"description": f"نمونهٔ چاپ سه‌بعدی (حلقه و زنجیر) — {i}",
                       "quantity": "۲", "unit_price": "۱٬۲۳۴٫۵۶۷۸", "line_total": "۲٬۴۶۹٫۱۳۵۶"}
                      for i in range(lines)],
            "subtotal": "۲٬۴۶۹٫۱۳۵۶", "discount": "۰", "total": probe,
        },
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", required=True, type=Path, help="Directory containing app/")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_root.resolve()))
    from app.services.pdf import render_html, render_pdf

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, lines, minimum in (("single-page", 1, 1), ("multi-page", 100, 2)):
        context = fixture_context(lines)
        html = render_html("proforma.html", context)
        if "<script>alert(1)</script>" in html or "&lt;script&gt;" not in html:
            raise ValueError("Customer text must remain escaped")
        if html.count("data:font/ttf;base64,") != 2:
            raise ValueError("Browser fallback must have both fonts inline")
        data = render_pdf("proforma.html", context)
        result = inspect_pdf(data, expected_digits=DIGITS, min_pages=minimum)
        if lines == 1 and result["pages"] != 1:
            raise ValueError("Single-page fixture overflowed")
        (args.out_dir / f"{name}.pdf").write_bytes(data)
        results[name] = result
    results["native_dll_paths"] = loaded_native_paths()
    results["scope"] = "Synthetic native rendering only; NOT installed payload or business/visual acceptance"
    report = json.dumps(results, ensure_ascii=False, indent=2)
    (args.out_dir / "proof.json").write_text(report, encoding="utf-8")
    print(report)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        annotation = json.dumps(results, ensure_ascii=True).replace("%", "%25")
        print(f"::notice title=Native PDF font proof::{annotation}")
    print("PASS: real A4 PDFs; used embedded Vazirmatn Regular/Bold; all 30 digits in both weights")


if __name__ == "__main__":
    main()

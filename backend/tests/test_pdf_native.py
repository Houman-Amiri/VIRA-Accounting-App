"""Inspector negative controls are synthetic PDFs, NOT native rendering proof."""

from __future__ import annotations

import io
import sys
from types import ModuleType

import pytest
from fontTools.ttLib import TTFont
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from app.services import pdf

DIGITS = "0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"


def sample_pdf(*, fault: str = "") -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612 if fault == "paper" else 595.28, height=841.89)
    resources = DictionaryObject()
    for index, weight in enumerate(("Regular", "Bold"), 1):
        raw = (pdf.FONTS_DIR / f"Vazirmatn-{weight}.ttf").read_bytes()
        if fault == "family" and index == 2:
            with TTFont(io.BytesIO(raw)) as font:
                for record in font["name"].names:
                    if record.nameID == 1:
                        record.string = "Arial".encode(record.getEncoding())
                buffer = io.BytesIO()
                font.save(buffer)
                raw = buffer.getvalue()
        stream = DecodedStreamObject()
        stream.set_data(raw)
        descriptor = DictionaryObject()
        if fault != "unembedded":
            descriptor[NameObject("/FontFile2")] = writer._add_object(stream)
        descendant = DictionaryObject({NameObject("/FontDescriptor"): descriptor})
        mapping = DecodedStreamObject()
        digits = (DIGITS[:-1] + "A") if fault == "digits" and index == 2 else DIGITS
        pairs = "\n".join(f"<{i:04x}> <{ord(c):04x}>" for i, c in enumerate(digits, 1))
        mapping.set_data(f"{len(digits)} beginbfchar\n{pairs}\nendbfchar".encode())
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/Encoding"): NameObject("/Identity-H"),
            NameObject("/BaseFont"): NameObject(f"/ABCDEF+Vazirmatn-{weight}"),
            NameObject("/DescendantFonts"): ArrayObject([descendant]),
        })
        if fault != "unicode":
            font[NameObject("/ToUnicode")] = writer._add_object(mapping)
        resources[NameObject(f"/F{index}")] = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): resources})
    content = DecodedStreamObject()
    all_codes = "".join(f"{i:04x}" for i in range(1, len(DIGITS) + 1)).encode()
    bold_codes = b"0001" if fault == "unused-mapped-digits" else all_codes
    content.set_data(b"BT /F1 12 Tf <" + all_codes + b"> Tj" + (
        b"" if fault == "unused-bold" else b" /F2 12 Tf [<" + bold_codes + b"> 10 <0002>] TJ"
    ) + b" ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_inspector_reads_embedded_font_bytes_and_used_weights(pdf_inspector):
    result = pdf_inspector(sample_pdf(), expected_digits=DIGITS)
    assert result["pages"] == 1
    assert {font["weight"] for font in result["fonts"]} == {400, 700}
    assert all(font["digits"] == DIGITS for font in result["fonts"])
    assert pdf_inspector(sample_pdf(), expected_by_weight={400: "۰۱۲", 700: "۷۸۹"})
    with pytest.raises(ValueError, match="weight 700"):
        pdf_inspector(sample_pdf(fault="unused-mapped-digits"), expected_by_weight={700: "۹"})


@pytest.mark.parametrize("fault,match", [
    ("paper", "A4"), ("family", "Non-Vazirmatn"),
    ("unembedded", "Embedded TrueType"), ("unicode", "Unicode map"),
    ("digits", "Digits missing from weight 700"),
    ("unused-bold", "Both Regular and Bold"),
    ("unused-mapped-digits", "Digits missing from weight 700"),
])
def test_inspector_rejects_false_positive_proofs(pdf_inspector, fault, match):
    with pytest.raises(ValueError, match=match):
        pdf_inspector(sample_pdf(fault=fault), expected_digits=DIGITS)


def test_inspector_rejects_html_and_insufficient_pages(pdf_inspector):
    with pytest.raises(ValueError, match="HTML fallback"):
        pdf_inspector(b"<!doctype html><title>Vazirmatn</title>")
    with pytest.raises(ValueError, match="page count"):
        pdf_inspector(sample_pdf(), min_pages=2)


def test_native_fetcher_allows_only_exact_bundled_fonts(monkeypatch):
    captured = {}
    weasy = ModuleType("weasyprint")
    fonts = ModuleType("weasyprint.text.fonts")
    urls = ModuleType("weasyprint.urls")
    fonts.FontConfiguration = object
    class URLFetcher:
        def __init__(self, **kwargs):
            assert kwargs == {"allowed_protocols": {"file"}, "allow_redirects": False, "fail_on_errors": True}

    class Response:
        def __init__(self, url, body, headers):
            self.url, self.body, self.headers = url, body, headers

    class FatalError(BaseException):
        pass

    weasy.URLFetcher = URLFetcher
    urls.URLFetcherResponse = Response
    urls.FatalURLFetchingError = FatalError

    class HTML:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def write_pdf(self, **kwargs):
            assert "font_config" in kwargs
            if captured.get("fail_font_load"):
                raise FatalError("missing bundled font")
            return b"mock renderer bytes, never native proof"

    weasy.HTML = HTML
    monkeypatch.setitem(sys.modules, "weasyprint", weasy)
    monkeypatch.setitem(sys.modules, "weasyprint.urls", urls)
    monkeypatch.setitem(sys.modules, "weasyprint.text.fonts", fonts)
    context = {"company": {"name": "VIRA", "tagline": ""}, "order": {
        "order_number": "1", "customer": {}, "lines": [],
    }}
    assert pdf.render_pdf("proforma.html", context) == b"mock renderer bytes, never native proof"
    fetch = captured["url_fetcher"].fetch
    for weight in ("Regular", "Bold"):
        uri = (pdf.FONTS_DIR / f"Vazirmatn-{weight}.ttf").as_uri()
        response = fetch(uri)
        assert response.body == (pdf.FONTS_DIR / f"Vazirmatn-{weight}.ttf").read_bytes()
        assert response.headers == {"Content-Type": "font/ttf"}
        assert uri in captured["string"]
    for forbidden in ("https://example.invalid/a.ttf", "http://127.0.0.1/", (pdf.FONTS_DIR.parent / "not-a-font.txt").as_uri(), "data:text/plain,not-a-font"):
        with pytest.raises(ValueError, match="Only the bundled"):
            fetch(forbidden)

    captured["fail_font_load"] = True
    with pytest.raises(RuntimeError, match="Bundled PDF fonts"):
        pdf.render_pdf("proforma.html", context)


async def test_fallback_is_explicit_html_with_self_contained_fonts(client, monkeypatch):
    from .test_operations import _order

    def unavailable(*args, **kwargs):
        raise RuntimeError("deliberately unavailable native libraries")

    monkeypatch.setattr(pdf, "render_pdf", unavailable)
    order = await _order(client)
    response = await client.get(f"/api/v1/orders/{order['id']}/proforma.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["content-disposition"].endswith('.html"')
    csp = response.headers["content-security-policy"]
    assert "font-src data:" in csp and "default-src 'none'" in csp
    assert "script-src" not in csp  # inherits none, never unsafe-inline scripts
    assert "frame-ancestors 'none'" in csp and "base-uri 'none'" in csp
    assert response.text.count("data:font/ttf;base64,") == 2
    assert "۲٬۷۶۰٬۷۴۸٫۵" in response.text

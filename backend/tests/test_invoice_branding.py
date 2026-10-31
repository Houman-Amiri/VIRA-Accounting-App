"""The printed invoice carries the owner's logo and the V.I.R.A name.

The mark is inlined as a data: PNG so a printed/previewed invoice stays
self-contained: no file path on the customer's machine, no network fetch, and
nothing for the printable CSP to block.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from app.services.pdf import (
    BRANDING_DIR,
    LOGO_FILENAME,
    PRINTABLE_HTML_CSP,
    logo_data_uri,
    render_html,
)

ORDER = {
    "order_number": "1001",
    "order_date": "2026-10-31",
    "order_date_jalali": "۱۴۰۵/۰۸/۰۹",
    "customer": {"name": "آقای رضایی", "phone": "۰۹۱۲۰۰۰۰۰۰۰", "address": "تهران"},
    "lines": [
        {
            "description": "مجسمهٔ روباه",
            "quantity": "۲",
            "unit_price": "۲٬۷۶۰٬۷۴۸٫۵",
            "line_total": "۵٬۵۲۱٬۴۹۷",
        }
    ],
    "subtotal": "۵٬۵۲۱٬۴۹۷",
    "discount": "۰",
    "total": "۵٬۵۲۱٬۴۹۷",
}
COMPANY = {"name": "V.I.R.A", "tagline": "چاپ سه‌بعدی و فروش محصولات"}


def test_the_invoice_header_shows_the_logo_and_the_name():
    html = render_html("proforma.html", {"company": COMPANY, "order": ORDER})
    assert '<img class="brand-logo" src="data:image/png;base64,' in html
    assert '<div class="brand-name">V.I.R.A</div>' in html
    assert COMPANY["tagline"] in html
    # the title still says what the document is
    assert "پیش‌فاکتور فروش" in html


def test_the_logo_is_the_real_shared_png_not_a_placeholder():
    uri = logo_data_uri()
    payload = base64.b64decode(uri.removeprefix("data:image/png;base64,"))
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert payload == (BRANDING_DIR / LOGO_FILENAME).read_bytes()
    assert len(payload) > 5_000


def test_the_printable_csp_allows_only_inline_images():
    assert "img-src data:" in PRINTABLE_HTML_CSP
    assert "default-src 'none'" in PRINTABLE_HTML_CSP
    # No http(s) or file: source is ever allowed for the printable document.
    assert "http" not in PRINTABLE_HTML_CSP


def test_a_non_png_asset_is_refused_instead_of_printed(monkeypatch, tmp_path: Path):
    fake = tmp_path / LOGO_FILENAME
    fake.write_bytes(b"not a png at all")
    monkeypatch.setattr("app.services.pdf.BRANDING_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="not a PNG"):
        logo_data_uri()


def test_the_invoice_html_stays_one_self_contained_document():
    html = render_html("proforma.html", {"company": COMPANY, "order": ORDER})
    # two Vazirmatn faces + the logo, all inline; nothing fetched from outside
    assert html.count("data:font/ttf;base64,") == 2
    assert html.count("data:image/png;base64,") == 1
    assert not re.search(r'src="(?!data:image/png)', html)


def test_the_document_date_is_jalali_in_persian_digits():
    from app.services.persian import jalali

    assert jalali("2026-10-31") == "۱۴۰۵/۰۸/۰۹"
    # an unparsable date still renders (ISO text) instead of breaking the page
    assert jalali("not-a-date") == "not-a-date"

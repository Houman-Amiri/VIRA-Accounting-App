"""Pinned, self-hosted Vazirmatn covers printed Persian/Arabic/Latin digits."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from app.services.pdf import render_html

FONTS = Path(__file__).resolve().parents[1] / "app/assets/fonts"


@pytest.mark.parametrize(
    "weight,digest",
    [
        ("Regular", "b69fd4c680b8f3f225feabcc655a2c585d97627b8f5f5c0f9985e894069f3a56"),
        ("Bold", "f635fdbea28f265de395ba83b4b1570dcf2f58d13c65469e61903b1c2d2ae723"),
    ],
)
def test_shipped_font_family_and_numeric_glyphs(weight, digest):
    path = FONTS / f"Vazirmatn-{weight}.ttf"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with TTFont(path) as font:
        assert font["name"].getDebugName(1) == "Vazirmatn"
        glyphs = font.getBestCmap()
        assert all(ord(c) in glyphs for c in "0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")
    assert "SIL OPEN FONT LICENSE" in (FONTS / "OFL.txt").read_text()


def test_proforma_numbers_use_local_vazirmatn_without_changing_values():
    order = {
        "order_number": "۱۲۳",
        "order_date": "2026-10-17",
        "customer": {"name": "تست", "phone": "۰۹۱۲۳۴۵۶۷۸۹", "address": "تهران"},
        "lines": [
            {
                "description": "نمونه",
                "quantity": "2",
                "unit_price": "123.4567",
                "line_total": "246.9134",
            }
        ],
        "subtotal": "246.9134",
        "discount": "0",
        "total": "246.9134",
    }
    html = render_html(
        "proforma.html", {"company": {"name": "VIRA", "tagline": "تست"}, "order": order}
    )
    assert "JetBrains" not in html
    assert "font-family: Vazirmatn" in html
    assert "@font-face" in html
    embedded = re.findall(r'data:font/ttf;base64,([A-Za-z0-9+/=]+)', html)
    assert len(embedded) == 2
    for encoded, weight in zip(embedded, ("Regular", "Bold"), strict=True):
        assert base64.b64decode(encoded) == (FONTS / f"Vazirmatn-{weight}.ttf").read_bytes()
    assert "direction: ltr; unicode-bidi: isolate" in html
    assert "123.4567" in html and "246.9134" in html

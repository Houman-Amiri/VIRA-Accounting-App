"""PDF generation (WeasyPrint) from Jinja2 templates — PDF documents only.

Jinja2 is used exclusively for server-rendered printable documents (invoices,
statements, price calculations).  WeasyPrint is imported lazily so the rest of
the backend works on hosts without native Pango/Cairo libraries.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
FONTS_DIR = TEMPLATES_DIR.parent / "assets" / "fonts"


def render_html(
    template_name: str, context: dict[str, Any], *, inline_fonts: bool = True
) -> str:
    """Printable HTML is self-contained, including the browser fallback fonts."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False,
    )
    template = env.get_template(template_name)
    font_urls = {}
    for weight in ("Regular", "Bold"):
        path = FONTS_DIR / f"Vazirmatn-{weight}.ttf"
        font_urls[f"font_{weight.lower()}_url"] = (
            "data:font/ttf;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
            if inline_fonts else path.as_uri()
        )
    return template.render(**context, **font_urls)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    html = render_html(template_name, context, inline_fonts=False)
    try:
        from weasyprint import HTML, default_url_fetcher  # type: ignore[import-untyped]
        from weasyprint.text.fonts import FontConfiguration  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - depends on host libs
        raise RuntimeError(
            "WeasyPrint is not available on this host (Pango/Cairo missing); "
            "install native prerequisites to enable PDF output"
        ) from exc
    allowed_urls = {
        (FONTS_DIR / f"Vazirmatn-{weight}.ttf").as_uri() for weight in ("Regular", "Bold")
    }

    def fetch_font(url: str) -> dict[str, Any]:
        # Printable documents must never fetch remote resources or arbitrary files.
        if url not in allowed_urls:
            raise ValueError("Only the bundled Vazirmatn font files may be fetched")
        return default_url_fetcher(url)

    return HTML(string=html, base_url=str(TEMPLATES_DIR), url_fetcher=fetch_font).write_pdf(
        font_config=FontConfiguration()
    )


def proforma_context(order: dict[str, Any]) -> dict[str, Any]:
    """Build the rendering context for a sales proforma invoice."""
    return {
        "company": {
            "name": "V.I.R.A",
            "tagline": "فروشگاه محصولات سه‌بعدی",
            "address": "",
            "phone": "",
        },
        "order": order,
        "json_debug": json.dumps(order, ensure_ascii=False, indent=2),
    }

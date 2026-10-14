"""PDF generation (WeasyPrint) from Jinja2 templates — PDF documents only.

Jinja2 is used exclusively for server-rendered printable documents (invoices,
statements, price calculations).  WeasyPrint is imported lazily so the rest of
the backend works on hosts without native Pango/Cairo libraries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


def render_html(template_name: str, context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False,
    )
    template = env.get_template(template_name)
    return template.render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    html = render_html(template_name, context)
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - depends on host libs
        raise RuntimeError(
            "WeasyPrint is not available on this host (Pango/Cairo missing); "
            "install native prerequisites to enable PDF output"
        ) from exc
    return HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()


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

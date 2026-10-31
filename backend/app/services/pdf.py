"""PDF generation (WeasyPrint) from Jinja2 templates — PDF documents only.

Jinja2 is used exclusively for server-rendered printable documents (invoices,
statements, price calculations).  WeasyPrint is imported lazily so the rest of
the backend works on hosts without native Pango/Fontconfig/HarfBuzz libraries.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
FONTS_DIR = TEMPLATES_DIR.parent / "assets" / "fonts"
BRANDING_DIR = TEMPLATES_DIR.parent / "assets" / "branding"
LOGO_FILENAME = "vira-logo.png"
#: PNG signature — the shared asset must really be a PNG before it is inlined.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PRINTABLE_HTML_CSP = (
    # The logo travels inside the document as a data: image, so the printable
    # HTML stays self-contained and never fetches anything over the network.
    "default-src 'none'; font-src data:; img-src data:; style-src 'unsafe-inline'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"
)


def logo_data_uri() -> str:
    """The V.I.R.A mark as a self-contained data: URI (no network, no file URLs)."""
    path = BRANDING_DIR / LOGO_FILENAME
    raw = path.read_bytes()
    if not raw.startswith(_PNG_SIGNATURE):
        raise RuntimeError(f"{LOGO_FILENAME} is not a PNG")
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


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
    company = context.get("company") or {}
    font_urls: dict[str, str] = {"logo_url": logo_data_uri()}
    context = {
        **context,
        "brand": {
            "logo_url": font_urls["logo_url"],
            "name": company.get("name") or "V.I.R.A",
            "tagline": company.get("tagline") or "",
        },
    }
    for weight in ("Regular", "Bold"):
        path = FONTS_DIR / f"Vazirmatn-{weight}.ttf"
        font_urls[f"font_{weight.lower()}_url"] = (
            "data:font/ttf;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
            if inline_fonts else path.as_uri()
        )
    return template.render(**context, **font_urls)


def render_pdf(
    template_name: str, context: dict[str, Any], *, font_configuration: Any | None = None
) -> bytes:
    # Explicit injection for private Unicode bootstrap QA; normal callers retain
    # their existing native configuration. No runtime is auto-enabled or shipped.
    html = render_html(template_name, context, inline_fonts=False)
    try:
        from weasyprint import HTML, URLFetcher  # type: ignore[import-untyped]
        from weasyprint.text.fonts import FontConfiguration  # type: ignore[import-untyped]
        from weasyprint.urls import (  # type: ignore[import-untyped]
            FatalURLFetchingError,
            URLFetcherResponse,
        )
    except Exception as exc:  # pragma: no cover - depends on host libs
        raise RuntimeError(
            "Native PDF engine could not be imported; check the WeasyPrint version "
            "and Pango/Fontconfig/HarfBuzz runtime (see chained cause)"
        ) from exc
    allowed_urls = {
        (FONTS_DIR / f"Vazirmatn-{weight}.ttf").as_uri(): FONTS_DIR / f"Vazirmatn-{weight}.ttf"
        for weight in ("Regular", "Bold")
    }

    class BundledFontFetcher(URLFetcher):
        def fetch(self, url: str, headers: dict[str, str] | None = None) -> Any:
            # No network/openers: read only the two exact bundled font paths.
            if url not in allowed_urls:
                raise ValueError("Only the bundled Vazirmatn font files may be fetched")
            return URLFetcherResponse(
                url, allowed_urls[url].read_bytes(), {"Content-Type": "font/ttf"}
            )

    fetcher = BundledFontFetcher(
        allowed_protocols={"file"}, allow_redirects=False, fail_on_errors=True
    )
    try:
        return HTML(string=html, base_url=str(TEMPLATES_DIR), url_fetcher=fetcher).write_pdf(
            font_config=FontConfiguration() if font_configuration is None else font_configuration
        )
    except FatalURLFetchingError as exc:
        # WeasyPrint's fatal resource errors inherit BaseException. Normalize
        # this specific case so the existing printable fallback still applies.
        raise RuntimeError("Bundled PDF fonts could not be loaded") from exc


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

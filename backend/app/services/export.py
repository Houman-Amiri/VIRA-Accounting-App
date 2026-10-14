"""CSV export with formula-injection sanitization (Phase 5 §7).

Cells starting with ``=``, ``+``, ``-``, ``@``, tab or CR are prefixed with an
apostrophe so spreadsheet apps treat them as text (OWASP CSV injection).
Amount columns remain exact fixed-scale strings — no float formatting.
"""

from __future__ import annotations

import csv
import io

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith(_DANGEROUS_PREFIXES):
        return "'" + text
    return text


def write_csv_safe(rows: list[dict[str, object]], columns: list[str]) -> str:
    """Render rows as CSV text with every cell sanitized."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([sanitize_csv_cell(c) for c in columns])
    for row in rows:
        writer.writerow([sanitize_csv_cell(row.get(c, "")) for c in columns])
    return buf.getvalue()

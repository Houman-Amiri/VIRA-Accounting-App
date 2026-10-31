"""Persian presentation for printed documents (digits, grouping, Jalali dates).

Presentation only: every value the ledger stores stays in Rials as scaled
integers; this module turns a number or an ISO date into what a Persian paper
document shows. Babel and jdatetime are optional — when they are missing the
document still renders (plain grouping, ISO date) instead of failing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
RIAL_PER_TOMAN = 10


def fa_group(value: Decimal, pattern: str) -> str:
    """Grouped number with Persian digits (fa_IR separators, ٫ decimal)."""
    try:
        from babel.numbers import format_decimal

        # fa_IR keeps Latin digits and Latin separators unless the arabext
        # numbering system is requested — then digits are transliterated below.
        text = format_decimal(
            value, format=pattern, locale="fa_IR", numbering_system="arabext"
        )
    except Exception:  # noqa: BLE001 - Babel missing → plain grouping
        text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text.translate(_FA_DIGITS)


def fa_money(value: Decimal | None) -> str:
    """Persian-grouped Toman, exact (fraction kept only when non-zero)."""
    decimal = Decimal(value or 0)
    pattern = "#,##0" if decimal == decimal.to_integral_value() else "#,##0.####"
    return fa_group(decimal, pattern)


def fa_money_from_rial(value: Decimal | None) -> str:
    """A Rial amount as the Toman a Persian invoice prints (÷10, exactly once)."""
    decimal = Decimal(value or 0) / RIAL_PER_TOMAN
    return fa_money(decimal)


def fa_count(value: Decimal | None) -> str:
    """A quantity: grouped, but never shown as money with trailing zeros."""
    decimal = Decimal(value or 0)
    normalized = decimal.normalize()
    pattern = "#,##0" if decimal == decimal.to_integral_value() else "#,##0.####"
    return fa_group(normalized, pattern)


def jalali(iso: str) -> str:
    """ISO date → Jalali «YYYY/MM/DD» (falls back to the ISO text)."""
    try:
        import jdatetime

        parsed = date.fromisoformat(iso)
        return jdatetime.date.fromgregorian(date=parsed).strftime("%Y/%m/%d")
    except Exception:  # noqa: BLE001 - the document still renders with the ISO date
        return iso

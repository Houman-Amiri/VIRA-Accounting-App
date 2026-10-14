"""Exact monetary arithmetic utilities.

Money is stored in SQLite as scaled INTEGER values:
    stored_amount = Decimal_amount * MONEY_SCALE   (scale = 10_000, i.e. 4 decimals)
FX rates are stored scaled by FX_SCALE = 100_000_000 (8 decimals).

Native ``float`` is forbidden for financial calculations anywhere in the app;
only :class:`decimal.Decimal` is used at the application layer, with
``ROUND_HALF_EVEN`` (banker's rounding) at the presentation boundary.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

MONEY_SCALE: Final[int] = 10_000
MONEY_EXPONENT: Final[int] = -4
FX_SCALE: Final[int] = 100_000_000
FX_EXPONENT: Final[int] = -8

#: Documented bounds: |amount| must stay below this many currency units so the
#: scaled integer always fits comfortably inside SQLite's signed 64-bit range
#: even after aggregation (2**63-1 / 10_000 ≈ 9.22e14).
MAX_ABS_AMOUNT: Final[Decimal] = Decimal("100000000000000")  # 1e14
MAX_ABS_FX_RATE: Final[Decimal] = Decimal("100000000")  # 1e8

_QUANT_MONEY = Decimal(1).scaleb(MONEY_EXPONENT)  # 0.0001
_QUANT_FX = Decimal(1).scaleb(FX_EXPONENT)  # 0.00000001


class MoneyError(ValueError):
    """Raised for any invalid monetary conversion, quantization or overflow."""


def quantize_money(value: Decimal) -> Decimal:
    """Quantize to 4 decimal places with banker's rounding."""
    if not isinstance(value, Decimal):
        raise MoneyError(f"monetary values must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise MoneyError("monetary values must be finite")
    try:
        q = value.quantize(_QUANT_MONEY, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise MoneyError(f"cannot quantize {value!r}") from exc
    if abs(q) >= MAX_ABS_AMOUNT:
        raise MoneyError(f"amount {q} exceeds safe bound {MAX_ABS_AMOUNT}")
    return q


def to_scaled(value: Decimal | str | int) -> int:
    """Convert an exact decimal amount to a scaled integer (×10 000)."""
    amount: Decimal
    if isinstance(value, bool):
        raise MoneyError("unsupported amount type: bool")
    if isinstance(value, str):
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise MoneyError(f"invalid decimal string: {value!r}") from exc
    elif isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    else:
        raise MoneyError(f"unsupported amount type: {type(value).__name__}")
    q = quantize_money(amount)
    scaled = int(q * MONEY_SCALE)
    if scaled != q * MONEY_SCALE:  # pragma: no cover - quantize guarantees this
        raise MoneyError("scaled conversion lost precision")
    return scaled


def from_scaled(scaled: int) -> Decimal:
    """Convert a scaled integer back to an exact :class:`Decimal`."""
    if isinstance(scaled, bool) or not isinstance(scaled, int):
        raise MoneyError(f"scaled amount must be int, got {type(scaled).__name__}")
    if abs(scaled) >= MAX_ABS_AMOUNT * MONEY_SCALE:
        raise MoneyError(f"scaled amount {scaled} exceeds safe bound")
    return Decimal(scaled) / MONEY_SCALE


def money_str(value: Decimal | str | int | None) -> str | None:
    """Serialize money as a fixed-scale string (e.g. ``"1250.5000"``) for JSON APIs."""
    if value is None:
        return None
    amount: Decimal
    if isinstance(value, bool):
        raise MoneyError("unsupported amount type: bool")
    if isinstance(value, int):
        # interpret as scaled integer only when explicitly requested
        amount = from_scaled(value)
    elif isinstance(value, str):
        amount = Decimal(value)
    else:
        amount = value
    return format(quantize_money(amount), f".{-MONEY_EXPONENT}f")


def parse_money_str(value: str | None) -> Decimal | None:
    """Parse a JSON money string into a quantized :class:`Decimal`."""
    if value is None:
        return None
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise MoneyError(f"invalid money string: {value!r}") from exc
    return quantize_money(dec)


def to_scaled_fx(rate: Decimal | str) -> int:
    """Convert an FX rate to a scaled integer (×100 000 000)."""
    if isinstance(rate, str):
        rate = Decimal(rate)
    if not isinstance(rate, Decimal) or not rate.is_finite():
        raise MoneyError("FX rate must be a finite Decimal")
    if rate <= 0:
        raise MoneyError("FX rate must be positive")
    if rate >= MAX_ABS_FX_RATE:
        raise MoneyError(f"FX rate {rate} exceeds safe bound")
    q = rate.quantize(_QUANT_FX, rounding=ROUND_HALF_EVEN)
    scaled = int(q * FX_SCALE)
    return scaled


def from_scaled_fx(scaled: int) -> Decimal:
    """Convert a scaled FX integer back to :class:`Decimal`."""
    if isinstance(scaled, bool) or not isinstance(scaled, int):
        raise MoneyError("scaled FX rate must be int")
    rate = Decimal(scaled) / FX_SCALE
    if rate <= 0:
        raise MoneyError("FX rate must be positive")
    return rate


def convert_scaled(
    amount_scaled: int,
    rate_scaled: int,
    *,
    to_functional: bool = True,
) -> int:
    """Convert a scaled amount between currencies using a scaled FX rate.

    ``to_functional=True`` multiplies by the rate; ``False`` divides.  All math
    is exact ``Decimal``; the result is quantized with banker's rounding.
    """
    amount = from_scaled(amount_scaled)
    rate = from_scaled_fx(rate_scaled)
    raw = amount * rate if to_functional else amount / rate
    return to_scaled(raw)


def safe_sum_scaled(values: list[int] | tuple[int, ...]) -> int:
    """Sum scaled integers with an explicit 64-bit overflow guard."""
    total = 0
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int):
            raise MoneyError(f"scaled values must be int, got {type(v).__name__}")
        total += v
        if abs(total) >= MAX_ABS_AMOUNT * MONEY_SCALE:
            raise MoneyError("aggregate exceeds safe scaled-integer bound")
    return total

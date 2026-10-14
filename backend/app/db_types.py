"""Central SQLAlchemy ``TypeDecorator`` money/rate types.

Phase 4 §1 mandates that the persistence layer expose :class:`decimal.Decimal`
values to services while persisting scaled INTEGERs:

* money  → ``stored = Decimal × 10 000``  (:data:`~app.money.MONEY_SCALE`)
* FX rate → ``stored = Decimal × 100 000 000`` (:data:`~app.money.FX_SCALE`)

These decorators run :func:`app.money.to_scaled` / :func:`app.money.to_scaled_fx`
on every bind, so quantization (banker's rounding) and overflow guards apply at
the write boundary no matter which code path persists a row.  Result-set
processing returns exact ``Decimal`` values.

The existing service layer also uses the same helpers directly on raw integer
columns; both paths converge on identical scaled integers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, TypeDecorator
from sqlalchemy.engine import Dialect

from .money import from_scaled, from_scaled_fx, to_scaled, to_scaled_fx


class ScaledMoneyType(TypeDecorator):
    """Exact 4-decimal money as scaled INTEGER (×10 000) in SQLite.

    Python side: :class:`decimal.Decimal`.  DB side: ``INTEGER`` (STRICT-safe).
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return to_scaled(value)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return to_scaled(Decimal(value) if isinstance(value, str) else value)
        raise TypeError(f"ScaledMoneyType expects Decimal|str|int, got {type(value).__name__}")

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return from_scaled(int(value))


class ScaledFxRateType(TypeDecorator):
    """Exact 8-decimal FX rate as scaled INTEGER (×1e8) in SQLite."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return to_scaled_fx(value)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return to_scaled_fx(Decimal(value))
        raise TypeError(f"ScaledFxRateType expects Decimal|str|int, got {type(value).__name__}")

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return from_scaled_fx(int(value))

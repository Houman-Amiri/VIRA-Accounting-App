"""Unit tests for exact monetary arithmetic (no float anywhere)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.money import (
    MAX_ABS_AMOUNT,
    MoneyError,
    convert_scaled,
    from_scaled,
    from_scaled_fx,
    money_str,
    parse_money_str,
    safe_sum_scaled,
    to_scaled,
    to_scaled_fx,
)


def test_to_scaled_basic() -> None:
    assert to_scaled(Decimal("1250.5")) == 12_505_000
    assert to_scaled("0.0001") == 1
    assert to_scaled(0) == 0
    assert to_scaled("-3.25") == -32_500


def test_round_trip_exact() -> None:
    for value in ["0", "1", "123456.7891", "-0.0001", "999999999.9999"]:
        scaled = to_scaled(Decimal(value))
        assert from_scaled(scaled) == Decimal(value).quantize(Decimal("0.0001"))


def test_bankers_rounding() -> None:
    # ROUND_HALF_EVEN: 0.00005 -> 0.0000 (round to even), 0.00015 -> 0.0002
    assert to_scaled("0.00005") == 0
    assert to_scaled("0.00015") == 2
    assert to_scaled("0.00025") == 2  # half-even on the scaled digit


def test_overflow_rejected() -> None:
    with pytest.raises(MoneyError):
        to_scaled(MAX_ABS_AMOUNT)
    with pytest.raises(MoneyError):
        from_scaled(10**18)


def test_float_rejected_by_type() -> None:
    with pytest.raises(MoneyError):
        to_scaled(1.5)  # type: ignore[arg-type]


def test_money_str_format() -> None:
    assert money_str(Decimal("1250.5")) == "1250.5000"
    assert money_str(None) is None
    assert parse_money_str("99.9999") == Decimal("99.9999")
    with pytest.raises(MoneyError):
        parse_money_str("not-a-number")


def test_fx_scale() -> None:
    assert to_scaled_fx("1.00000000") == 100_000_000
    assert to_scaled_fx("1.12345678") == 112_345_678
    assert from_scaled_fx(100_000_000) == Decimal("1")
    with pytest.raises(MoneyError):
        to_scaled_fx("0")
    with pytest.raises(MoneyError):
        to_scaled_fx("-2")


def test_convert_scaled() -> None:
    # 100.0000 EUR at rate 1.10 -> 110.0000 USD
    amount = to_scaled("100")
    rate = to_scaled_fx("1.10")
    assert convert_scaled(amount, rate) == to_scaled("110")
    assert convert_scaled(to_scaled("110"), rate, to_functional=False) == to_scaled("100")


def test_safe_sum_guard() -> None:
    assert safe_sum_scaled([1, 2, 3]) == 6
    with pytest.raises(MoneyError):
        safe_sum_scaled([10**18])

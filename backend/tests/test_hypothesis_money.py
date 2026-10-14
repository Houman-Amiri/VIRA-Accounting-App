"""Property-based financial tests (Hypothesis).

Randomized multi-split transactions and edge-case decimals must never violate
double-entry balance invariants or lose precision.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.money import (
    convert_scaled,
    from_scaled,
    money_str,
    parse_money_str,
    to_scaled,
    to_scaled_fx,
)
from app.schemas.ledger import JournalEntryCreate, SplitCreate

amounts = st.decimals(
    min_value=Decimal("-999999999"),
    max_value=Decimal("999999999"),
    places=4,
    allow_nan=False,
    allow_infinity=False,
)


@settings(max_examples=100, deadline=None)
@given(value=amounts)
def test_scaled_round_trip_property(value: Decimal) -> None:
    scaled = to_scaled(value)
    assert from_scaled(scaled) == value
    assert parse_money_str(money_str(value)) == value


@settings(max_examples=100, deadline=None)
@given(value=amounts)
def test_money_str_is_exact_fixed_scale(value: Decimal) -> None:
    s = money_str(value)
    assert s is not None and len(s.split(".")[1]) == 4
    assert Decimal(s) == value


@settings(max_examples=100, deadline=None)
@given(debit=amounts.filter(lambda d: d > 0))
def test_balanced_entry_always_validates(debit: Decimal) -> None:
    entry = JournalEntryCreate(
        transaction_date="2026-10-14",
        description="property",
        splits=[
            SplitCreate(account_id="a", debit=money_str(debit)),
            SplitCreate(account_id="b", credit=money_str(debit)),
        ],
    )
    scaled = entry.scaled_splits()
    assert scaled[0]["debit"] == scaled[1]["credit"]
    assert scaled[0]["functional_debit"] == scaled[1]["functional_credit"]


@settings(max_examples=100, deadline=None)
@given(
    parts=st.lists(amounts.filter(lambda d: d > 0), min_size=1, max_size=9),
)
def test_multi_split_balanced_entry(parts: list[Decimal]) -> None:
    splits = []
    for amount in parts:
        splits.append(SplitCreate(account_id="x", debit=money_str(amount)))
        splits.append(SplitCreate(account_id="y", credit=money_str(amount)))
    entry = JournalEntryCreate(
        transaction_date="2026-10-14", description="multi", splits=splits
    )
    scaled = entry.scaled_splits()
    total_d = sum(int(s["debit"]) for s in scaled)
    total_c = sum(int(s["credit"]) for s in scaled)
    assert total_d == total_c


@settings(max_examples=80, deadline=None)
@given(amount=amounts.filter(lambda d: d != 0), rate=st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("100"), places=8, allow_nan=False
))
def test_fx_conversion_preserves_precision(amount: Decimal, rate: Decimal) -> None:
    scaled_amount = to_scaled(amount)
    scaled_rate = to_scaled_fx(rate)
    converted = convert_scaled(scaled_amount, scaled_rate)
    back = convert_scaled(converted, scaled_rate, to_functional=False)
    # two conversions with banker's rounding — error stays well under 1 currency unit
    assert abs(back - scaled_amount) <= 1000

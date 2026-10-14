"""Pydantic double-entry validation rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ledger import JournalEntryCreate, SplitCreate


def _split(debit: str = "0", credit: str = "0", **kw) -> SplitCreate:
    return SplitCreate(account_id=kw.pop("account_id", "acc"), debit=debit, credit=credit, **kw)


def test_split_requires_exactly_one_side() -> None:
    with pytest.raises(ValidationError):
        _split(debit="0", credit="0")
    with pytest.raises(ValidationError):
        _split(debit="5", credit="5")
    with pytest.raises(ValidationError):
        _split(debit="-5", credit="0")
    _split(debit="5", credit="0")
    _split(debit="0", credit="5")


def test_entry_needs_two_splits() -> None:
    with pytest.raises(ValidationError):
        JournalEntryCreate(
            transaction_date="2026-10-14",
            description="x",
            splits=[_split(debit="5")],
        )


def test_entry_must_balance_per_currency() -> None:
    with pytest.raises(ValidationError):
        JournalEntryCreate(
            transaction_date="2026-10-14",
            description="unbalanced",
            splits=[_split(debit="10"), _split(credit="9")],
        )


def test_entry_balanced_ok() -> None:
    entry = JournalEntryCreate(
        transaction_date="2026-10-14",
        description="balanced",
        splits=[_split(debit="10.5"), _split(credit="10.5")],
    )
    scaled = entry.scaled_splits()
    assert scaled[0]["debit"] == 105_000
    assert scaled[1]["credit"] == 105_000


def test_multi_currency_must_balance_per_currency() -> None:
    with pytest.raises(ValidationError):
        JournalEntryCreate(
            transaction_date="2026-10-14",
            description="fx unbalanced",
            splits=[
                _split(debit="100", currency="EUR"),
                _split(credit="110", currency="USD"),  # different currency: unbalanced
            ],
        )
    entry = JournalEntryCreate(
        transaction_date="2026-10-14",
        description="fx ok",
        splits=[
            _split(debit="100", currency="EUR"),
            _split(credit="100", currency="EUR"),
            _split(debit="110", currency="USD"),
            _split(credit="110", currency="USD"),
        ],
    )
    assert len(entry.scaled_splits()) == 4


def test_invalid_date_rejected() -> None:
    with pytest.raises(ValidationError):
        JournalEntryCreate(
            transaction_date="14-10-2026",
            description="x",
            splits=[_split(debit="1"), _split(credit="1")],
        )


def test_money_string_normalized() -> None:
    entry = JournalEntryCreate(
        transaction_date="2026-10-14",
        description="x",
        splits=[_split(debit="1.5"), _split(credit="1.5")],
    )
    assert entry.splits[0].debit == "1.5000"

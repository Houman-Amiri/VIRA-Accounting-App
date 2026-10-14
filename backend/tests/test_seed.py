"""Seed scripts must be idempotent (safe to run more than once)."""

from __future__ import annotations

from app.seed import seed_all


def test_seed_all_idempotent(session) -> None:
    first = seed_all(session, admin_password="pw-12345678")
    assert first["accounts_created"] > 0
    second = seed_all(session, admin_password="pw-12345678")
    assert second["accounts_created"] == 0  # nothing duplicated
    from sqlalchemy import func, select

    from app.models import Account, User

    count = session.scalar(select(func.count()).select_from(Account))
    assert count == first["accounts_created"]
    users = session.scalar(select(func.count()).select_from(User))
    assert users == 1  # owner only (plus nothing else)


def test_seed_currencies_and_opening_equity(session) -> None:
    from sqlalchemy import func, select

    from app.models import Currency
    from app.seed import seed_all

    result = seed_all(session, admin_password="pw-12345678")
    assert result["currencies_created"] == 6
    assert result["accounts_created"] > 0

    base = session.get(Currency, "IRR")
    assert base is not None and base.is_base == 1
    codes = set(session.scalars(select(Currency.code)))
    assert {"IRR", "USD", "EUR", "AED", "TRY", "GBP"} <= codes

    # opening-balance equity exists in the business chart
    from app.models import Account

    obe = session.scalar(select(Account).where(Account.code == "3900"))
    assert obe is not None
    assert obe.account_type == "EQUITY"

    # re-run creates nothing new
    again = seed_all(session, admin_password="pw-12345678")
    assert again["currencies_created"] == 0
    assert again["accounts_created"] == 0
    assert again["users_created"] == 0
    assert session.scalar(select(func.count()).select_from(Currency)) == 6


def test_seed_personal_chart(session) -> None:
    from sqlalchemy import select

    from app.models import Account
    from app.seed import seed_all

    result = seed_all(session, chart="personal", admin_password="pw-12345678")
    assert result["accounts_created"] > 0
    name = session.scalar(select(Account.name).where(Account.code == "5010"))
    assert name == "خوراک و سوپرمارکت"
    obe = session.scalar(select(Account).where(Account.code == "3900"))
    assert obe is not None

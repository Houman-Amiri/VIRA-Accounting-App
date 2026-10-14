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

"""SQLite single-writer concurrency + overflow guards (Phase 4 §2/§4)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.ids import uuid7
from app.money import MoneyError, safe_sum_scaled, to_scaled
from app.schemas.ledger import JournalEntryCreate, SplitCreate
from app.services.ledger import LedgerService


def _mk_accounts(session, n: int = 2) -> list[str]:
    ids = []
    for i in range(n):
        aid = uuid7()
        code = f"73{i}0"
        session.execute(
            text(
                "INSERT INTO accounts (id, code, name, account_type, normal_balance,"
                " currency, parent_id, path, is_placeholder, is_active, version_id)"
                " VALUES (:id, :code, 'c', 'ASSET', 'DEBIT', 'IRR', NULL, :code, 0, 1, 1)"
            ),
            {"id": aid, "code": code},
        )
        ids.append(aid)
    session.commit()
    return ids


def test_concurrent_inserts_all_succeed_with_immediate_retry(database, session) -> None:
    a, b = _mk_accounts(session)
    errors: list[Exception] = []

    def _worker(i: int) -> None:
        try:
            with database.write_session() as s:
                LedgerService(s).create_draft(
                    JournalEntryCreate(
                        transaction_date="2026-10-14",
                        description=f"concurrent {i}",
                        splits=[
                            SplitCreate(account_id=a, debit="1.0000"),
                            SplitCreate(account_id=b, credit="1.0000"),
                        ],
                    )
                )
        except Exception as exc:  # pragma: no cover - failure surfaces below
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_worker, range(8)))

    assert not errors, errors
    count = session.execute(
        text("SELECT COUNT(*) FROM journal_entries WHERE description LIKE 'concurrent %'")
    ).scalar()
    assert int(count) == 8


def test_concurrent_post_of_same_draft_transitions_once(database, session) -> None:
    """Serialized writers: exactly ONE DRAFT→POSTED transition despite a race.

    ``post()`` is idempotent for already-POSTED entries, so both callers may
    succeed — the invariant is a single version bump and consistent state.
    """
    a, b = _mk_accounts(session)
    service = LedgerService(session)
    entry = service.create_draft(
        JournalEntryCreate(
            transaction_date="2026-10-14",
            description="race target",
            splits=[
                SplitCreate(account_id=a, debit="5.0000"),
                SplitCreate(account_id=b, credit="5.0000"),
            ],
        )
    )
    entry_id = entry.id
    session.commit()

    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def _poster() -> None:
        barrier.wait()
        try:
            with database.write_session() as s:
                LedgerService(s).post(entry_id)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    t1 = threading.Thread(target=_poster)
    t2 = threading.Thread(target=_poster)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, errors
    row = session.execute(
        text("SELECT status, version_id FROM journal_entries WHERE id=:id"),
        {"id": entry_id},
    ).one()
    assert row[0] == "POSTED"
    assert row[1] == 2, "exactly one version bump — no double transition"


def test_overflow_rejected_at_money_boundary() -> None:
    with pytest.raises(MoneyError):
        to_scaled(Decimal("1e14"))
    with pytest.raises(MoneyError):
        safe_sum_scaled([2**62, 2**62, 2**62])


def test_bulk_aggregation_respects_documented_bounds() -> None:
    """Aggregates are guarded at MAX_ABS_AMOUNT × scale (1e18) — no wraparound."""
    rows = [to_scaled(Decimal("9e12")) for _ in range(10)]  # 9e16 scaled total
    total = safe_sum_scaled(rows)
    assert total == to_scaled(Decimal("9e13"))
    assert total < 2**63 - 1
    with pytest.raises(MoneyError):
        safe_sum_scaled([to_scaled(Decimal("9e13")) for _ in range(2)])  # 1.8e18 > bound

"""Phase 7 §1 — unified search: numeric tokens (Decimal→scaled), split-memo
coverage, entry_number matching, FTS5 and LIKE paths stay in agreement."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ids import uuid7
from app.services.search import _numeric_scales, search


def _seed(session: Session) -> str:
    acc1, acc2, entry_id = uuid7(), uuid7(), uuid7()
    for acc_id, code, name in ((acc1, "1010", "صندوق"), (acc2, "6010", "فروش خدمات")):
        session.execute(
            text(
                "INSERT INTO accounts (id, code, name, account_type, normal_balance, currency,"
                " parent_id, path, is_placeholder, is_active, version_id)"
                " VALUES (:id, :code, :name, 'ASSET', 'DEBIT', 'IRR', NULL, :code, 0, 1, 1)"
            ),
            {"id": acc_id, "code": code, "name": name},
        )
    session.execute(
        text(
            "INSERT INTO journal_entries (id, entry_number, transaction_date, posted_at,"
            " payee, description, status, reversed_entry_id, metadata_json, version_id,"
            " created_at, updated_at)"
            " VALUES (:id, 123, '2026-10-14', '2026-10-14T00:00:00', 'شرکت نوین',"
            " 'فروش پرینت سه‌بعدی', 'DRAFT', NULL, '{}', 1,"
            " '2026-10-14T00:00:00', '2026-10-14T00:00:00')"
        ),
        {"id": entry_id},
    )
    for split_id, acc_id, debit, credit, memo in (
        (uuid7(), acc1, 15005000, 0, "پیش‌پرداخت نقدی مشتری"),
        (uuid7(), acc2, 0, 15005000, None),
    ):
        session.execute(
            text(
                "INSERT INTO transaction_splits (id, journal_entry_id, account_id,"
                " reconciliation_session_id, memo, debit, credit, currency, exchange_rate,"
                " functional_debit, functional_credit, reconciliation_status)"
                " VALUES (:id, :je, :acc, NULL, :memo, :debit, :credit, 'IRR', 100000000,"
                " :debit, :credit, 'UNRECONCILED')"
            ),
            {
                "id": split_id,
                "je": entry_id,
                "acc": acc_id,
                "memo": memo,
                "debit": debit,
                "credit": credit,
            },
        )
    session.commit()
    return entry_id


@pytest.mark.parametrize("force_like", [False, True])
def test_unified_search_memo_payee_entry_number(session: Session, force_like: bool) -> None:
    entry_id = _seed(session)
    # payee
    hits = search(session, "نوین", force_like=force_like)
    assert any(h.ref_id == entry_id for h in hits)
    # split memo (Phase 7 §1 — unified fields incl. transaction_splits.memo)
    hits = search(session, "پیش‌پرداخت", force_like=force_like)
    assert any(h.ref_id == entry_id for h in hits)
    # entry number
    hits = search(session, "123", force_like=force_like)
    assert any(h.ref_id == entry_id for h in hits)


def test_numeric_token_decimal_scaled_amount_match(session: Session) -> None:
    entry_id = _seed(session)
    # 1500.5000 parses via Decimal and maps to the stored scaled value exactly
    scales = _numeric_scales("1500.5000")
    assert scales == [15005000]
    for force_like in (False, True):
        hits = search(session, "1500.5000", force_like=force_like)
        assert any(h.ref_id == entry_id for h in hits), force_like
    # garbage/overflow numeric tokens never crash
    assert _numeric_scales("abc") == []
    assert all(abs(s) < 10**18 for s in _numeric_scales("1e9999999999"))


def test_search_deduplicates_and_bounds(session: Session) -> None:
    _seed(session)
    hits = search(session, "پیش‌پرداخت", limit=5)
    keys = [(h.entity, h.ref_id) for h in hits]
    assert len(keys) == len(set(keys))
    assert len(hits) <= 5

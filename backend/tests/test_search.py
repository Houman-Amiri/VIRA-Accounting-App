"""Search: FTS5 path, LIKE fallback, trigger-maintained index (Phase 4 §8)."""

from __future__ import annotations

from sqlalchemy import text

from app.ids import uuid7
from app.services.search import has_fts, search


def _seed_entry(session, description: str, payee: str | None = None) -> str:
    entry_id = uuid7()
    acc_id = uuid7()
    code = f"7{abs(hash(entry_id)) % 90000:05d}"
    session.execute(
        text(
            "INSERT INTO accounts (id, code, name, account_type, normal_balance, currency,"
            " parent_id, path, is_placeholder, is_active, version_id)"
            " VALUES (:id, :code, 'جستجو حساب', 'ASSET', 'DEBIT', 'IRR', NULL, :code, 0, 1, 1)"
        ),
        {"id": acc_id, "code": code},
    )
    session.execute(
        text(
            "INSERT INTO journal_entries (id, entry_number, transaction_date, posted_at,"
            " payee, description, status, reversed_entry_id, metadata_json, version_id,"
            " created_at, updated_at)"
            " VALUES (:id, abs(random()) % 900000 + 100000, '2026-03-01',"
            " '2026-03-01T00:00:00', :payee, :desc, 'DRAFT', NULL, '{}', 1,"
            " '2026-03-01T00:00:00', '2026-03-01T00:00:00')"
        ),
        {"id": entry_id, "payee": payee, "desc": description},
    )
    session.commit()
    return entry_id


def test_fts5_available_in_this_build(session) -> None:
    assert has_fts(session) is True


def test_fts_finds_entries_and_keeps_sync_on_update_delete(session) -> None:
    entry_id = _seed_entry(session, "خرید فیلامنت PLA سفید", payee="پارس پرینت")
    hits = search(session, "فیلامنت", entity="entry")
    assert any(h.ref_id == entry_id for h in hits)

    session.execute(
        text(f"UPDATE journal_entries SET description='فروش پایه موبایل' WHERE id='{entry_id}'")
    )
    session.commit()
    assert search(session, "فیلامنت", entity="entry") == []
    assert any(h.ref_id == entry_id for h in search(session, "پایه موبایل", entity="entry"))

    session.execute(text(f"DELETE FROM journal_entries WHERE id='{entry_id}'"))
    session.commit()
    assert search(session, "پایه موبایل", entity="entry") == []


def test_fts_prefix_matching_and_accounts(session) -> None:
    _seed_entry(session, "پرداخت اجاره دفتر")
    hits = search(session, "پرداخ", entity="entry")  # prefix token
    assert hits, "prefix matching should find پرداخت"
    acc_hits = search(session, "جستجو", entity="account")
    assert any(h.entity == "account" for h in acc_hits)


def test_like_fallback_matches_fts_results(session) -> None:
    entry_id = _seed_entry(session, "حقوق و دستمزد مهر", payee="کارمند")
    fts = search(session, "دستمزد", entity="entry")
    like = search(session, "دستمزد", entity="entry", force_like=True)
    assert {h.ref_id for h in fts} & {entry_id}
    assert {h.ref_id for h in like} & {entry_id}


def test_empty_query_returns_nothing(session) -> None:
    assert search(session, "   ") == []

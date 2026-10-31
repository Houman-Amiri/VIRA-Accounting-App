"""Ledger service: posting invariants, immutability triggers, fiscal locks."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.ids import uuid7
from app.models import FiscalPeriod, JournalEntry
from app.schemas.ledger import (
    AccountCreate,
    JournalEntryCreate,
    JournalEntryUpdate,
    SplitCreate,
)
from app.services.errors import (
    ClosedFiscalPeriodError,
    EntryNotDraftError,
    EntryReconciledError,
    InsufficientSplitsError,
    NotFoundError,
    PlaceholderAccountError,
    StaleVersionError,
    UnbalancedJournalEntryError,
)
from app.services.ledger import LedgerService
from app.services.reporting import ReportingService


def _accounts(service: LedgerService) -> dict[str, object]:
    cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
    eq = service.create_account(
        AccountCreate(code="3010", name="سرمایه", account_type="EQUITY")
    )
    rev = service.create_account(AccountCreate(code="4010", name="فروش", account_type="INCOME"))
    exp = service.create_account(AccountCreate(code="5040", name="اجاره", account_type="EXPENSE"))
    ph = service.create_account(
        AccountCreate(code="1000", name="دارایی", account_type="ASSET", is_placeholder=True)
    )
    return {"cash": cash, "equity": eq, "revenue": rev, "expense": exp, "placeholder": ph}


def _entry(cash_id: str, eq_id: str, *, date: str = "2026-10-14", amount: str = "1000"):
    return JournalEntryCreate(
        transaction_date=date,
        description="test entry",
        splits=[
            SplitCreate(account_id=cash_id, debit=amount),
            SplitCreate(account_id=eq_id, credit=amount),
        ],
    )


def test_create_and_post(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.create_draft(_entry(accs["cash"].id, accs["equity"].id))
    assert entry.status == "DRAFT"
    posted = service.post(entry.id)
    assert posted.status == "POSTED"
    assert len(posted.splits) == 2
    debit_split = next(s for s in posted.splits if s.debit > 0)
    assert debit_split.functional_debit == 10_000_000  # 1000 × 10^4


def test_unbalanced_draft_rejected_at_post(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    data = _entry(accs["cash"].id, accs["equity"].id)
    # craft unbalanced splits directly through scaled insert path
    entry = service.create_draft(data)
    credit_split = next(s for s in entry.splits if s.credit > 0)
    credit_split.credit = credit_split.credit - 1
    session.flush()  # make the tampered value visible to validation
    with pytest.raises(UnbalancedJournalEntryError):
        service.post(entry.id)
    session.rollback()


def test_insufficient_splits_rejected(session) -> None:
    from pydantic import ValidationError

    service = LedgerService(session)
    accs = _accounts(service)
    with pytest.raises(ValidationError):
        JournalEntryCreate.model_validate(
            {
                "transaction_date": "2026-10-14",
                "description": "x",
                "splits": [{"account_id": accs["cash"].id, "debit": "5"}],
            }
        )
    entry = service.create_draft(_entry(accs["cash"].id, accs["equity"].id))
    session.commit()  # persist setup before a mid-test rollback
    session.delete(entry.splits[1])
    session.flush()
    with pytest.raises(InsufficientSplitsError):
        service.post(entry.id)


def test_placeholder_account_rejected(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    with pytest.raises(PlaceholderAccountError):
        service.create_draft(_entry(accs["placeholder"].id, accs["equity"].id))


def test_posted_entry_immutable_via_triggers(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    session.commit()  # persist accounts so mid-test rollbacks keep setup

    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    session.flush()

    # deletion blocked by trigger
    session.delete(entry)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    # financial edit of splits blocked by trigger
    fresh = LedgerService(session)
    entry2 = fresh.post(fresh.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    session.flush()
    entry2.splits[0].debit = 999
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_reverse_creates_contra(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    contra = service.reverse(entry.id)
    assert contra.status == "POSTED"
    assert contra.reversed_entry_id == entry.id
    original_sides = {(s.account_id, s.debit, s.credit) for s in entry.splits}
    contra_sides = {(s.account_id, s.credit, s.debit) for s in contra.splits}
    assert original_sides == contra_sides  # every side mirrored


def test_void_only_posted(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    draft = service.create_draft(_entry(accs["cash"].id, accs["equity"].id))
    with pytest.raises(EntryNotDraftError):
        service.void(draft.id)
    posted = service.post(draft.id)
    voided = service.void(posted.id, reason="mistake")
    assert voided.status == "VOIDED"


def test_fiscal_period_lock(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    session.add(
        FiscalPeriod(
            id=uuid7(),
            name="مهر ۱۴۰۵",
            start_date="2026-09-23",
            end_date="2026-10-22",
            is_closed=1,
            closed_at="2026-10-23T00:00:00Z",
        )
    )
    session.flush()
    with pytest.raises(ClosedFiscalPeriodError):
        service.create_draft(_entry(accs["cash"].id, accs["equity"].id, date="2026-10-14"))
    # trigger is a secondary guard too
    entry = JournalEntry(
        id=uuid7(),
        entry_number=9999,
        transaction_date="2026-10-14",
        posted_at="2026-10-14T00:00:00Z",
        description="bypass attempt",
        status="DRAFT",
        metadata_json="{}",
        version_id=1,
        created_at="2026-10-14T00:00:00Z",
        updated_at="2026-10-14T00:00:00Z",
    )
    session.add(entry)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_optimistic_locking(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    from app.schemas.ledger import AccountUpdate

    account = accs["cash"]
    updated = service.update_account(account.id, AccountUpdate(name="صندوق نقد", version_id=1))
    assert updated.version_id == 2
    with pytest.raises(StaleVersionError):
        service.update_account(account.id, AccountUpdate(name="دوباره", version_id=1))


def test_entry_number_sequential(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    e1 = service.create_draft(_entry(accs["cash"].id, accs["equity"].id))
    e2 = service.create_draft(_entry(accs["cash"].id, accs["equity"].id))
    assert e2.entry_number == e1.entry_number + 1


def test_not_found(session) -> None:
    service = LedgerService(session)
    with pytest.raises(NotFoundError):
        service.get_entry("missing")


def test_edit_draft_replaces_lines_and_keeps_history(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.create_draft(_entry(accs["cash"].id, accs["equity"].id, amount="1000"))
    session.commit()
    before_version = entry.version_id

    updated = service.update_entry(
        entry.id,
        JournalEntryUpdate(
            transaction_date="2026-10-15",
            description="اصلاح شرح",
            payee="آقای رضایی",
            version_id=before_version,
            splits=[
                SplitCreate(account_id=accs["cash"].id, debit="2500"),
                SplitCreate(account_id=accs["equity"].id, credit="2500"),
            ],
        ),
    )
    session.commit()
    assert updated.transaction_date == "2026-10-15"
    assert updated.description == "اصلاح شرح"
    assert updated.version_id == before_version + 1
    assert sum(s.debit for s in updated.splits) == 25_000_000  # 2500 × 10^4


def test_stale_edit_is_refused(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.create_draft(_entry(accs["cash"].id, accs["equity"].id))
    with pytest.raises(StaleVersionError):
        service.update_entry(
            entry.id,
            JournalEntryUpdate(
                transaction_date="2026-10-14", description="x", version_id=entry.version_id + 1
            ),
        )


def test_posted_entry_can_only_be_corrected_through_unpost(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    session.commit()

    with pytest.raises(EntryNotDraftError):
        service.update_entry(
            entry.id, JournalEntryUpdate(transaction_date="2026-10-14", description="x")
        )

    corrected = service.correct_entry(
        entry.id,
        JournalEntryUpdate(
            transaction_date="2026-10-16",
            description="اصلاح مبلغ",
            splits=[
                SplitCreate(account_id=accs["cash"].id, debit="700"),
                SplitCreate(account_id=accs["equity"].id, credit="700"),
            ],
        ),
    )
    session.commit()
    assert corrected.status == "POSTED"
    assert corrected.transaction_date == "2026-10-16"
    assert sum(s.debit for s in corrected.splits) == 7_000_000


def test_unpost_returns_a_posted_entry_to_draft(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    session.commit()
    unposted = service.unpost(entry.id)
    session.commit()
    assert unposted.status == "DRAFT"
    # the books no longer count it
    rows = ReportingService(session).trial_balance(as_of="2026-12-31")
    assert rows == []


def test_unpost_refused_when_the_line_is_reconciled(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    session.commit()
    entry.splits[0].reconciliation_status = "CLEARED"
    session.commit()

    with pytest.raises(EntryReconciledError):
        service.unpost(entry.id)
    session.rollback()


def test_unpost_refused_after_a_reversal_exists(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    service.reverse(entry.id, transaction_date="2026-10-20")
    session.commit()
    from app.services.errors import DomainError

    with pytest.raises(DomainError):
        service.unpost(entry.id)
    session.rollback()


def test_voided_entry_cannot_be_edited(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    service.void(entry.id, reason="اشتباه")
    session.commit()
    with pytest.raises(EntryNotDraftError):
        service.update_entry(
            entry.id, JournalEntryUpdate(transaction_date="2026-10-14", description="x")
        )
    session.rollback()


def test_edit_refused_into_a_closed_period(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.create_draft(_entry(accs["cash"].id, accs["equity"].id, date="2026-10-20"))
    session.add(
        FiscalPeriod(
            id=uuid7(),
            name="مهر ۱۴۰۵",
            start_date="2026-09-23",
            end_date="2026-10-22",
            is_closed=1,
            closed_at="2026-10-23T00:00:00Z",
        )
    )
    session.flush()
    with pytest.raises(ClosedFiscalPeriodError):
        service.update_entry(
            entry.id, JournalEntryUpdate(transaction_date="2026-10-14", description="x")
        )
    session.rollback()


def test_correct_entry_accepts_the_current_version_and_refuses_a_stale_one(session) -> None:
    service = LedgerService(session)
    accs = _accounts(service)
    entry = service.post(service.create_draft(_entry(accs["cash"].id, accs["equity"].id)).id)
    session.commit()
    current = entry.version_id

    with pytest.raises(StaleVersionError):
        service.correct_entry(
            entry.id,
            JournalEntryUpdate(
                transaction_date="2026-10-14", description="x", version_id=current + 5
            ),
        )
    fresh = LedgerService(session).get_entry(entry.id)
    start_version = fresh.version_id
    corrected = service.correct_entry(
        fresh.id,
        JournalEntryUpdate(
            transaction_date="2026-10-17", description="اصلاح", version_id=start_version
        ),
    )
    session.commit()
    assert corrected.status == "POSTED"
    assert corrected.description == "اصلاح"
    assert corrected.version_id > start_version

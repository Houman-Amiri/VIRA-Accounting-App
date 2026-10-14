"""Authoritative double-entry ledger service.

All posting mutations happen inside ONE write transaction (BEGIN IMMEDIATE):
insert/update splits → validate every invariant → set status → commit.  Any
failure rolls back everything.  Service-level validation is authoritative;
SQLite CHECKs/triggers are secondary guards.

Invariants:
* ≥ 2 valid split rows,
* exactly one positive side per split (debit XOR credit),
* Σ functional debits = Σ functional credits,
* no posting to placeholder accounts,
* posted entries are immutable (corrections via reversing entries),
* writes into closed fiscal periods are rejected.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ids import today_iso, utc_now_iso, uuid7
from ..models import Account, FiscalPeriod, JournalEntry, TransactionSplit
from ..schemas.ledger import (
    NORMAL_BY_TYPE,
    AccountCreate,
    AccountUpdate,
    JournalEntryCreate,
)
from ..services.audit import attach_old_snapshot
from ..services.errors import (
    ClosedFiscalPeriodError,
    EntryNotDraftError,
    InsufficientSplitsError,
    NotFoundError,
    PlaceholderAccountError,
    StaleVersionError,
    UnbalancedJournalEntryError,
)


class LedgerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------------- accounts ----------------

    def create_account(self, data: AccountCreate) -> Account:
        parent_path = ""
        if data.parent_id:
            parent = self.session.get(Account, data.parent_id)
            if parent is None:
                raise NotFoundError(f"parent account {data.parent_id} not found")
            parent_path = parent.path
        path = f"{parent_path}.{data.code}" if parent_path else data.code
        account = Account(
            id=uuid7(),
            code=data.code,
            name=data.name,
            account_type=data.account_type,
            normal_balance=NORMAL_BY_TYPE[data.account_type],
            currency=data.currency.upper(),
            parent_id=data.parent_id,
            path=path,
            is_placeholder=1 if data.is_placeholder else 0,
            is_active=1,
            version_id=1,
        )
        self.session.add(account)
        self.session.flush()
        return account

    def update_account(self, account_id: str, data: AccountUpdate) -> Account:
        account = self.get_account(account_id)
        attach_old_snapshot(account)
        if account.version_id != data.version_id:
            raise StaleVersionError(
                f"account {account.code} was modified concurrently "
                f"(expected version {data.version_id}, found {account.version_id})"
            )
        if data.name is not None:
            account.name = data.name
        if data.is_active is not None:
            account.is_active = 1 if data.is_active else 0
        account.version_id += 1
        self.session.flush()
        return account

    def get_account(self, account_id: str) -> Account:
        account = self.session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"account {account_id} not found")
        return account

    def list_accounts(self, *, active_only: bool = False) -> list[Account]:
        stmt = select(Account).order_by(Account.path)
        if active_only:
            stmt = stmt.where(Account.is_active == 1)
        return list(self.session.scalars(stmt))

    # ---------------- journal entries ----------------

    def next_entry_number(self) -> int:
        current = self.session.scalar(select(func.max(JournalEntry.entry_number))) or 0
        return int(current) + 1

    def create_draft(self, data: JournalEntryCreate, *, post: bool = False) -> JournalEntry:
        self._assert_period_open(data.transaction_date)
        entry = JournalEntry(
            id=uuid7(),
            entry_number=self.next_entry_number(),
            transaction_date=data.transaction_date,
            posted_at=utc_now_iso(),
            payee=data.payee,
            description=data.description,
            status="DRAFT",
            reversed_entry_id=None,
            metadata_json=json.dumps(data.metadata, ensure_ascii=False),
            version_id=1,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self.session.add(entry)
        self.session.flush()
        self._replace_splits(entry, data)
        self.session.flush()
        if post:
            return self.post(entry.id)
        return entry

    def update_draft(self, entry_id: str, data: JournalEntryCreate) -> JournalEntry:
        entry = self.get_entry(entry_id)
        if entry.status != "DRAFT":
            raise EntryNotDraftError(f"entry {entry.entry_number} is {entry.status}")
        self._assert_period_open(data.transaction_date)
        attach_old_snapshot(entry)
        entry.transaction_date = data.transaction_date
        entry.payee = data.payee
        entry.description = data.description
        entry.metadata_json = json.dumps(data.metadata, ensure_ascii=False)
        entry.updated_at = utc_now_iso()
        for sp in list(entry.splits):
            self.session.delete(sp)
        self.session.flush()
        self._replace_splits(entry, data)
        self.session.flush()
        return entry

    def post(self, entry_id: str) -> JournalEntry:
        entry = self.get_entry(entry_id)
        if entry.status == "POSTED":
            return entry
        if entry.status != "DRAFT":
            raise EntryNotDraftError(f"entry {entry.entry_number} is {entry.status} and cannot post")
        self._assert_period_open(entry.transaction_date)
        self.validate_entry(entry)
        attach_old_snapshot(entry)
        entry.status = "POSTED"
        entry.posted_at = utc_now_iso()
        entry.updated_at = utc_now_iso()
        entry.version_id += 1
        self.session.flush()
        return entry

    def void(self, entry_id: str, *, reason: str = "") -> JournalEntry:
        """Void a posted entry. Corrections normally use :meth:`reverse`."""
        entry = self.get_entry(entry_id)
        if entry.status != "POSTED":
            raise EntryNotDraftError(f"only POSTED entries can be voided (is {entry.status})")
        attach_old_snapshot(entry)
        entry.status = "VOIDED"
        entry.updated_at = utc_now_iso()
        meta = json.loads(entry.metadata_json or "{}")
        if reason:
            meta["void_reason"] = reason
        entry.metadata_json = json.dumps(meta, ensure_ascii=False)
        entry.version_id += 1
        self.session.flush()
        return entry

    def reverse(self, entry_id: str, *, transaction_date: str | None = None) -> JournalEntry:
        """Create a contra/reversing entry; the original stays immutable."""
        original = self.get_entry(entry_id)
        if original.status != "POSTED":
            raise EntryNotDraftError(
                f"only POSTED entries can be reversed (is {original.status})"
            )
        date = transaction_date or today_iso()
        self._assert_period_open(date)
        contra = JournalEntry(
            id=uuid7(),
            entry_number=self.next_entry_number(),
            transaction_date=date,
            posted_at=utc_now_iso(),
            payee=original.payee,
            description=f"Reversal of entry #{original.entry_number}: {original.description}",
            status="DRAFT",
            reversed_entry_id=original.id,
            metadata_json=json.dumps({"reverses": original.id}, ensure_ascii=False),
            version_id=1,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self.session.add(contra)
        self.session.flush()
        for sp in original.splits:
            self.session.add(
                TransactionSplit(
                    id=uuid7(),
                    journal_entry_id=contra.id,
                    account_id=sp.account_id,
                    memo=f"Reversal: {sp.memo or ''}".strip(),
                    debit=sp.credit,
                    credit=sp.debit,
                    currency=sp.currency,
                    exchange_rate=sp.exchange_rate,
                    functional_debit=sp.functional_credit,
                    functional_credit=sp.functional_debit,
                    reconciliation_status="UNRECONCILED",
                )
            )
        self.session.flush()
        self.validate_entry(contra)
        contra.status = "POSTED"
        contra.posted_at = utc_now_iso()
        contra.version_id += 1
        self.session.flush()
        return contra

    def get_entry(self, entry_id: str) -> JournalEntry:
        entry = self.session.get(JournalEntry, entry_id)
        if entry is None:
            raise NotFoundError(f"journal entry {entry_id} not found")
        return entry

    def list_entries(
        self, *, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[JournalEntry]:
        stmt = (
            select(JournalEntry)
            .order_by(JournalEntry.transaction_date.desc(), JournalEntry.entry_number.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(JournalEntry.status == status)
        return list(self.session.scalars(stmt))

    # ---------------- validation ----------------

    def validate_entry(self, entry: JournalEntry) -> None:
        # Query splits from the database — authoritative (relationship state
        # can be stale right after deletions).
        splits = list(
            self.session.scalars(
                select(TransactionSplit).where(
                    TransactionSplit.journal_entry_id == entry.id
                )
            )
        )
        if len(splits) < 2:
            raise InsufficientSplitsError(
                f"entry #{entry.entry_number} has {len(splits)} splits; at least 2 required"
            )
        totals: dict[str, int] = {}
        functional_total = 0
        for sp in splits:
            if sp.debit > 0 and sp.credit > 0:
                raise UnbalancedJournalEntryError("a split cannot have both debit and credit")
            if sp.debit <= 0 and sp.credit <= 0:
                raise UnbalancedJournalEntryError("a split must have a positive debit or credit")
            account = self.session.get(Account, sp.account_id)
            if account is None:
                raise NotFoundError(f"split account {sp.account_id} not found")
            if account.is_placeholder:
                raise PlaceholderAccountError(
                    f"account {account.code} is a placeholder and cannot be posted to"
                )
            totals[sp.currency] = totals.get(sp.currency, 0) + (sp.debit - sp.credit)
            functional_total += sp.functional_debit - sp.functional_credit
        unbalanced = {cur: d for cur, d in totals.items() if d != 0}
        if unbalanced:
            raise UnbalancedJournalEntryError(
                "debits must equal credits per currency: "
                + ", ".join(f"{cur} delta={d}" for cur, d in sorted(unbalanced.items()))
            )
        if functional_total != 0:
            raise UnbalancedJournalEntryError(
                f"functional debits must equal functional credits (delta={functional_total})"
            )

    # ---------------- internals ----------------

    def _assert_period_open(self, date: str) -> None:
        row = self.session.scalar(
            select(FiscalPeriod).where(
                FiscalPeriod.is_closed == 1,
                FiscalPeriod.start_date <= date,
                FiscalPeriod.end_date >= date,
            )
        )
        if row is not None:
            raise ClosedFiscalPeriodError(
                f"date {date} falls in closed fiscal period '{row.name}'"
            )

    def _replace_splits(self, entry: JournalEntry, data: JournalEntryCreate) -> None:
        if len(data.splits) < 2:
            raise InsufficientSplitsError("at least two split lines are required")
        for sp in data.scaled_splits():
            account_id = str(sp["account_id"])
            account = self.session.get(Account, account_id)
            if account is None:
                raise NotFoundError(f"split account {account_id} not found")
            if account.is_placeholder:
                raise PlaceholderAccountError(
                    f"account {account.code} is a placeholder and cannot be posted to"
                )
            self.session.add(
                TransactionSplit(
                    id=uuid7(),
                    journal_entry_id=entry.id,
                    account_id=account_id,
                    memo=sp["memo"],  # type: ignore[arg-type]
                    debit=int(str(sp["debit"])),
                    credit=int(str(sp["credit"])),
                    currency=str(sp["currency"]),
                    exchange_rate=int(str(sp["exchange_rate"])),
                    functional_debit=int(str(sp["functional_debit"])),
                    functional_credit=int(str(sp["functional_credit"])),
                    reconciliation_status="UNRECONCILED",
                )
            )

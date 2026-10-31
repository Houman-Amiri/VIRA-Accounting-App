"""Invoice-shaped journal entries — the simple «سند» the owner actually fills.

The double-entry engine stays untouched: this service derives the two balanced
splits from an invoice (date, seller, buyer, lines) using the seeded chart of
accounts, so the user never types debit/credit. The line detail is kept in the
entry metadata so the printed/listed entry can still show what was invoiced.

Never guesses: if the mapping accounts are absent (for example a personal
chart), it refuses with a Persian message instead of posting an unbalanced or
misleading entry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, JournalEntry
from ..money import parse_money_str
from ..schemas.ledger import (
    InvoiceCreate,
    InvoiceEntryUpdate,
    InvoiceLineRead,
    InvoiceRead,
    JournalEntryCreate,
    JournalEntryUpdate,
    SplitCreate,
)
from .errors import DomainError
from .ledger import LedgerService

QUANT = Decimal("0.0001")
ZERO = Decimal(0)

#: kind → (debit account code, credit account code, meaning in Persian).
#: Sale: receivable ↑ / sales revenue ↑. Purchase: inventory ↑ / payable ↑.
MAPPING: dict[str, tuple[str, str, str, str]] = {
    "sale": ("1040", "4010", "حساب‌های دریافتنی", "درآمد فروش محصولات"),
    "purchase": ("1030", "2010", "موجودی مواد و کالا", "حساب‌های پرداختنی"),
}


@dataclass(frozen=True)
class InvoiceTotals:
    lines: list[tuple[str, Decimal, Decimal, Decimal]]
    total: Decimal


def invoice_totals(data: InvoiceCreate) -> InvoiceTotals:
    rows: list[tuple[str, Decimal, Decimal, Decimal]] = []
    total = ZERO
    for line in data.lines:
        quantity = (parse_money_str(line.quantity) or ZERO).quantize(QUANT)
        unit_price = (parse_money_str(line.unit_price) or ZERO).quantize(QUANT)
        if quantity <= 0:
            raise DomainError("تعداد هر ردیف فاکتور باید بزرگ‌تر از صفر باشد")
        line_total = (quantity * unit_price).quantize(QUANT)
        rows.append((line.title.strip(), quantity, unit_price, line_total))
        total += line_total
    total = total.quantize(QUANT)
    if total <= 0:
        raise DomainError("مبلغ کل فاکتور باید بزرگ‌تر از صفر باشد")
    return InvoiceTotals(lines=rows, total=total)


def _account_by_code(session: Session, code: str, label: str) -> Account:
    account = session.scalar(select(Account).where(Account.code == code, Account.is_active == 1))
    if account is None:
        raise DomainError(
            f"حساب «{label}» با کد {code} در چارت حساب‌ها فعال نیست؛ "
            "پیش از ثبت فاکتور آن را در چارت حساب‌ها بسازید یا فعال کنید."
        )
    return account


def _money(value: Decimal) -> str:
    return f"{value.quantize(QUANT):.4f}"


def build_invoice_payload(
    session: Session, data: InvoiceCreate
) -> tuple[JournalEntryCreate, InvoiceTotals, Account, Account]:
    """Derive the balanced entry an invoice describes (no persistence)."""
    totals = invoice_totals(data)
    debit_code, credit_code, debit_label, credit_label = MAPPING[data.kind]
    debit = _account_by_code(session, debit_code, debit_label)
    credit = _account_by_code(session, credit_code, credit_label)

    party = (data.buyer if data.kind == "sale" else data.seller) or ""
    party = party.strip()
    verb = "فروش به" if data.kind == "sale" else "خرید از"
    description = (data.description or "").strip() or (
        f"{verb} {party} — {len(totals.lines)} قلم"
        if party
        else f"فاکتور {'فروش' if data.kind == 'sale' else 'خرید'} — {len(totals.lines)} قلم"
    )
    memo_parts = [f"{title} × {quantity.normalize()} = {_money(line_total)}" for title, quantity, _u, line_total in totals.lines]
    memo = "; ".join(memo_parts)[:480]
    metadata: dict[str, Any] = {
        "invoice": {
            "kind": data.kind,
            "seller": (data.seller or "").strip() or None,
            "buyer": (data.buyer or "").strip() or None,
            "note": (data.note or "").strip() or None,
            "lines": [
                {
                    "title": title,
                    "quantity": f"{quantity:.4f}",
                    "unit_price": _money(unit_price),
                    "line_total": _money(line_total),
                }
                for title, quantity, unit_price, line_total in totals.lines
            ],
        }
    }
    payload = JournalEntryCreate(
        transaction_date=data.transaction_date,
        payee=party or None,
        description=description,
        metadata=metadata,
        splits=[
            SplitCreate(account_id=debit.id, debit=_money(totals.total), memo=memo),
            SplitCreate(account_id=credit.id, credit=_money(totals.total), memo=memo),
        ],
    )
    return payload, totals, debit, credit


def create_invoice(session: Session, data: InvoiceCreate) -> InvoiceRead:
    """Build, post and return a balanced entry derived from an invoice."""
    payload, totals, debit, credit = build_invoice_payload(session, data)
    metadata = payload.metadata
    entry: JournalEntry = LedgerService(session).create_draft(payload, post=True)
    return InvoiceRead(
        entry=_entry_read(entry),
        kind=data.kind,
        seller=metadata["invoice"]["seller"],
        buyer=metadata["invoice"]["buyer"],
        total=_money(totals.total),
        lines=[
            InvoiceLineRead(
                title=title,
                quantity=f"{quantity:.4f}",
                unit_price=_money(unit_price),
                line_total=_money(line_total),
            )
            for title, quantity, unit_price, line_total in totals.lines
        ],
        debit_account=f"{debit.code} — {MAPPING[data.kind][2]}",
        credit_account=f"{credit.code} — {MAPPING[data.kind][3]}",
    )


def update_invoice_entry(
    session: Session, entry_id: str, data: InvoiceEntryUpdate
) -> InvoiceRead:
    """Correct an invoice-shaped entry; the server re-derives its splits.

    The entry keeps its status (a posted invoice stays posted) and its previous
    content is kept as a version snapshot by the ledger service.
    """
    entry = LedgerService(session).get_entry(entry_id)
    invoice_meta = (json.loads(entry.metadata_json or "{}") or {}).get("invoice")
    if not isinstance(invoice_meta, dict):
        raise DomainError(
            f"سند شماره {entry.entry_number} از فاکتور ساخته نشده است و با فرم فاکتور "
            "قابل ویرایش نیست"
        )
    payload, totals, debit, credit = build_invoice_payload(
        session,
        InvoiceCreate(
            transaction_date=data.transaction_date,
            kind=data.kind,
            seller=data.seller,
            buyer=data.buyer,
            description=data.description,
            note=data.note,
            lines=data.lines,
        ),
    )
    updated = LedgerService(session).correct_entry(
        entry_id,
        JournalEntryUpdate(
            transaction_date=payload.transaction_date,
            payee=payload.payee,
            description=payload.description,
            metadata=payload.metadata,
            splits=payload.splits,
            version_id=data.version_id,
        ),
    )
    metadata = payload.metadata
    return InvoiceRead(
        entry=_entry_read(updated),
        kind=data.kind,
        seller=metadata["invoice"]["seller"],
        buyer=metadata["invoice"]["buyer"],
        total=_money(totals.total),
        lines=[
            InvoiceLineRead(
                title=title,
                quantity=f"{quantity:.4f}",
                unit_price=_money(unit_price),
                line_total=_money(line_total),
            )
            for title, quantity, unit_price, line_total in totals.lines
        ],
        debit_account=f"{debit.code} — {MAPPING[data.kind][2]}",
        credit_account=f"{credit.code} — {MAPPING[data.kind][3]}",
    )


def _entry_read(entry: JournalEntry) -> Any:
    """Reuse the API's read model without importing the router (no cycle)."""
    from ..schemas.ledger import JournalEntryRead, SplitRead

    return JournalEntryRead(
        id=entry.id,
        entry_number=entry.entry_number,
        transaction_date=entry.transaction_date,
        posted_at=entry.posted_at,
        payee=entry.payee,
        description=entry.description,
        status=entry.status,  # type: ignore[arg-type]
        reversed_entry_id=entry.reversed_entry_id,
        metadata=json.loads(entry.metadata_json or "{}"),
        version_id=entry.version_id,
        splits=[SplitRead.from_row(s) for s in entry.splits],
    )

"""Ledger schemas with strict double-entry validation (Pydantic v2).

Invariants enforced before any persistence:
* every journal entry has at least two split lines,
* each split has exactly one positive side (debit XOR credit),
* Σ debits − Σ credits = 0 per currency,
* placeholder accounts cannot receive splits.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..money import (
    convert_scaled,
    from_scaled,
    from_scaled_fx,
    parse_money_str,
    to_scaled,
    to_scaled_fx,
)
from .common import CurrencyCode, ISODate, MoneyStr

AccountType = Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]
NormalBalance = Literal["DEBIT", "CREDIT"]
EntryStatus = Literal["DRAFT", "POSTED", "VOIDED"]
ReconciliationStatus = Literal["UNRECONCILED", "CLEARED", "RECONCILED"]


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    account_type: AccountType
    currency: CurrencyCode = "IRR"
    parent_id: str | None = None
    is_placeholder: bool = False

    @field_validator("code")
    @classmethod
    def _code_format(cls, v: str) -> str:
        if not v.replace(".", "").isalnum():
            raise ValueError("account code must be alphanumeric (dots allowed)")
        return v


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    version_id: int = Field(ge=1)


class AccountRead(BaseModel):
    id: str
    code: str
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    currency: str
    parent_id: str | None
    path: str
    is_placeholder: bool
    is_active: bool
    version_id: int

    model_config = {"from_attributes": True}


NORMAL_BY_TYPE: dict[str, NormalBalance] = {
    "ASSET": "DEBIT",
    "EXPENSE": "DEBIT",
    "LIABILITY": "CREDIT",
    "EQUITY": "CREDIT",
    "INCOME": "CREDIT",
}


class SplitCreate(BaseModel):
    account_id: str
    memo: str | None = None
    debit: MoneyStr = "0.0000"
    credit: MoneyStr = "0.0000"
    currency: CurrencyCode = "IRR"
    exchange_rate: str = "1.00000000"

    @model_validator(mode="after")
    def _one_side_positive(self) -> SplitCreate:
        d = parse_money_str(self.debit) or 0
        c = parse_money_str(self.credit) or 0
        if d < 0 or c < 0:
            raise ValueError("debit and credit must be non-negative")
        if (d > 0) == (c > 0):
            raise ValueError("exactly one of debit/credit must be positive")
        if to_scaled_fx(self.exchange_rate) <= 0:
            raise ValueError("exchange_rate must be positive")
        return self


class JournalEntryCreate(BaseModel):
    transaction_date: ISODate
    payee: str | None = None
    description: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    splits: list[SplitCreate] = Field(min_length=2)

    @model_validator(mode="after")
    def _balanced_per_currency(self) -> JournalEntryCreate:
        totals: dict[str, list[int]] = {}
        for sp in self.splits:
            side = "debit" if (parse_money_str(sp.debit) or 0) > 0 else "credit"
            amount = to_scaled(parse_money_str(sp.debit if side == "debit" else sp.credit) or 0)
            totals.setdefault(sp.currency, []).append(amount if side == "debit" else -amount)
        unbalanced = {
            cur: sum(vals) for cur, vals in totals.items() if sum(vals) != 0
        }
        if unbalanced:
            raise ValueError(
                "journal entry is unbalanced per currency: "
                + ", ".join(f"{cur} delta={delta}" for cur, delta in sorted(unbalanced.items()))
            )
        return self

    def scaled_splits(self) -> list[dict[str, int | str | None]]:
        """Return split dicts with scaled integer amounts (and functional amounts)."""
        out: list[dict[str, int | str | None]] = []
        for sp in self.splits:
            d = to_scaled(parse_money_str(sp.debit) or 0)
            c = to_scaled(parse_money_str(sp.credit) or 0)
            rate = to_scaled_fx(sp.exchange_rate)
            out.append(
                {
                    "account_id": sp.account_id,
                    "memo": sp.memo,
                    "debit": d,
                    "credit": c,
                    "currency": sp.currency,
                    "exchange_rate": rate,
                    "functional_debit": convert_scaled(d, rate) if d else 0,
                    "functional_credit": convert_scaled(c, rate) if c else 0,
                }
            )
        return out


class SplitRead(BaseModel):
    id: str
    account_id: str
    memo: str | None
    debit: str
    credit: str
    currency: str
    exchange_rate: str
    functional_debit: str
    functional_credit: str
    reconciliation_status: ReconciliationStatus

    @classmethod
    def from_row(cls, row: Any) -> SplitRead:
        return cls(
            id=row.id,
            account_id=row.account_id,
            memo=row.memo,
            debit=f"{from_scaled(row.debit):.4f}",
            credit=f"{from_scaled(row.credit):.4f}",
            currency=row.currency,
            exchange_rate=f"{from_scaled_fx(row.exchange_rate):.8f}",
            functional_debit=f"{from_scaled(row.functional_debit):.4f}",
            functional_credit=f"{from_scaled(row.functional_credit):.4f}",
            reconciliation_status=row.reconciliation_status,
        )


class JournalEntryRead(BaseModel):
    id: str
    entry_number: int
    transaction_date: str
    posted_at: str
    payee: str | None
    description: str
    status: EntryStatus
    reversed_entry_id: str | None
    metadata: dict[str, Any]
    version_id: int
    splits: list[SplitRead]


class AccountLedgerRow(BaseModel):
    """One posted movement on an account — the drill-down behind a statement line."""

    entry_id: str
    entry_number: int
    transaction_date: str
    description: str
    payee: str | None
    debit: str
    credit: str


class AccountLedgerRead(BaseModel):
    account_id: str
    code: str
    name: str
    account_type: AccountType
    start: str | None
    end: str | None
    opening_balance: str
    closing_balance: str
    total_debit: str
    total_credit: str
    rows: list[AccountLedgerRow]


class JournalEntryUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=500)
    payee: str | None = None
    version_id: int = Field(ge=1)


class TrialBalanceRow(BaseModel):
    account_id: str
    code: str
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    is_placeholder: bool
    debit: str
    credit: str
    balance: str


class ReportNode(BaseModel):
    account_id: str
    code: str
    name: str
    account_type: AccountType
    is_placeholder: bool
    amount: str
    children: list[ReportNode] = Field(default_factory=list)


class BalanceSheetReport(BaseModel):
    as_of: str
    assets: list[ReportNode]
    liabilities: list[ReportNode]
    equity: list[ReportNode]
    total_assets: str
    total_liabilities: str
    total_equity: str
    retained_earnings: str


class IncomeStatementReport(BaseModel):
    period_start: str
    period_end: str
    income: list[ReportNode]
    expenses: list[ReportNode]
    total_income: str
    total_expenses: str
    net_income: str


class CashFlowReport(BaseModel):
    period_start: str
    period_end: str
    opening_balance: str
    closing_balance: str
    inflows: str
    outflows: str
    net_change: str


# ------------------------------------------------------------- simple invoice ---
class InvoiceLineIn(BaseModel):
    """One invoice row the user actually sees: title, count, price."""

    title: str = Field(min_length=1, max_length=200)
    quantity: MoneyStr = "1.0000"
    unit_price: MoneyStr = "0.0000"

    @model_validator(mode="after")
    def _positive_quantity(self) -> InvoiceLineIn:
        if (parse_money_str(self.quantity) or 0) <= 0:
            raise ValueError("تعداد هر ردیف فاکتور باید بزرگ‌تر از صفر باشد")
        if (parse_money_str(self.unit_price) or 0) < 0:
            raise ValueError("مبلغ واحد نمی‌تواند منفی باشد")
        return self


class InvoiceCreate(BaseModel):
    """Invoice-shaped entry — the server derives the double-entry itself.

    The user fills what a paper invoice has (date, seller, buyer, lines); the
    chart-of-accounts mapping stays a server decision so the ledger's balance
    invariant is never exposed as a form field.
    """

    transaction_date: ISODate
    kind: Literal["sale", "purchase"]
    seller: str | None = Field(default=None, max_length=200)
    buyer: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _counterparty(self) -> InvoiceCreate:
        # Whom the money is owed by/to is not optional on a real invoice.
        if self.kind == "sale" and not (self.buyer or "").strip():
            raise ValueError("برای فاکتور فروش، نام خریدار را وارد کنید")
        if self.kind == "purchase" and not (self.seller or "").strip():
            raise ValueError("برای فاکتور خرید، نام فروشنده را وارد کنید")
        return self


class InvoiceLineRead(BaseModel):
    title: str
    quantity: str
    unit_price: str
    line_total: str


class InvoiceRead(BaseModel):
    entry: JournalEntryRead
    kind: Literal["sale", "purchase"]
    seller: str | None
    buyer: str | None
    total: str
    lines: list[InvoiceLineRead]
    debit_account: str
    credit_account: str

"""Reporting: recursive-CTE hierarchy rollups and Polars series."""

from __future__ import annotations

from app.schemas.ledger import AccountCreate, JournalEntryCreate, SplitCreate
from app.services.ledger import LedgerService
from app.services.reporting import ReportingService


def test_hierarchy_rollup_includes_children(session) -> None:
    service = LedgerService(session)
    parent = service.create_account(
        AccountCreate(code="1000", name="دارایی", account_type="ASSET", is_placeholder=True)
    )
    child_a = service.create_account(
        AccountCreate(code="1010", name="صندوق", account_type="ASSET", parent_id=parent.id)
    )
    child_b = service.create_account(
        AccountCreate(code="1020", name="بانک", account_type="ASSET", parent_id=parent.id)
    )
    eq = service.create_account(AccountCreate(code="3010", name="سرمایه", account_type="EQUITY"))

    service.create_draft(
        JournalEntryCreate(
            transaction_date="2026-10-01",
            description="a",
            splits=[
                SplitCreate(account_id=child_a.id, debit="100"),
                SplitCreate(account_id=eq.id, credit="100"),
            ],
        ),
        post=True,
    )
    service.create_draft(
        JournalEntryCreate(
            transaction_date="2026-10-02",
            description="b",
            splits=[
                SplitCreate(account_id=child_b.id, debit="250.5"),
                SplitCreate(account_id=eq.id, credit="250.5"),
            ],
        ),
        post=True,
    )
    session.flush()

    reports = ReportingService(session)
    bs = reports.balance_sheet("2026-12-31")
    # parent (1000) is inclusive of children
    top = next(n for n in bs.assets if n.code == "1000")
    assert top.amount == "350.5000"
    assert {c.code: c.amount for c in top.children} == {"1010": "100.0000", "1020": "250.5000"}
    assert bs.total_assets == "350.5000"


def test_income_statement_period_isolation(session) -> None:
    service = LedgerService(session)
    cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
    rev = service.create_account(AccountCreate(code="4010", name="فروش", account_type="INCOME"))
    exp = service.create_account(AccountCreate(code="5040", name="اجاره", account_type="EXPENSE"))

    for date, splits in [
        (
            "2026-01-15",
            [
                SplitCreate(account_id=cash.id, debit="1000"),
                SplitCreate(account_id=rev.id, credit="1000"),
            ],
        ),
        (
            "2026-06-15",
            [
                SplitCreate(account_id=cash.id, debit="2000"),
                SplitCreate(account_id=rev.id, credit="2000"),
            ],
        ),
        (
            "2026-06-20",
            [
                SplitCreate(account_id=exp.id, debit="400"),
                SplitCreate(account_id=cash.id, credit="400"),
            ],
        ),
    ]:
        service.create_draft(
            JournalEntryCreate(transaction_date=date, description="t", splits=splits),
            post=True,
        )
    session.flush()

    reports = ReportingService(session)
    q2 = reports.income_statement("2026-04-01", "2026-06-30")
    assert q2.total_income == "2000.0000"
    assert q2.total_expenses == "400.0000"
    assert q2.net_income == "1600.0000"

    year = reports.income_statement("2026-01-01", "2026-12-31")
    assert year.net_income == "2600.0000"

    series = reports.monthly_income_series("2026-01-01", "2026-12-31")
    assert series.height == 2
    months = series["month"].to_list()
    assert "2026-01" in months and "2026-06" in months


def test_cash_flow(session) -> None:
    service = LedgerService(session)
    cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
    rev = service.create_account(AccountCreate(code="4010", name="فروش", account_type="INCOME"))
    service.create_draft(
        JournalEntryCreate(
            transaction_date="2026-05-01",
            description="sale",
            splits=[
                SplitCreate(account_id=cash.id, debit="500"),
                SplitCreate(account_id=rev.id, credit="500"),
            ],
        ),
        post=True,
    )
    exp = service.create_account(AccountCreate(code="5040", name="اجاره", account_type="EXPENSE"))
    service.create_draft(
        JournalEntryCreate(
            transaction_date="2026-05-10",
            description="rent",
            splits=[
                SplitCreate(account_id=exp.id, debit="50"),
                SplitCreate(account_id=cash.id, credit="50"),
            ],
        ),
        post=True,
    )
    session.flush()
    reports = ReportingService(session)
    cf = reports.cash_flow("2026-05-01", "2026-05-31")
    assert cf.inflows == "500.0000"
    assert cf.outflows == "50.0000"
    assert cf.net_change == "450.0000"
    assert cf.closing_balance == "450.0000"


def test_trial_balance_checks_out(session) -> None:
    service = LedgerService(session)
    cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
    eq = service.create_account(AccountCreate(code="3010", name="سرمایه", account_type="EQUITY"))
    service.create_draft(
        JournalEntryCreate(
            transaction_date="2026-10-14",
            description="open",
            splits=[
                SplitCreate(account_id=cash.id, debit="42.0001"),
                SplitCreate(account_id=eq.id, credit="42.0001"),
            ],
        ),
        post=True,
    )
    session.flush()
    rows = ReportingService(session).trial_balance("2026-12-31")
    total_d = sum(round(float(r.debit) * 10000) for r in rows)
    total_c = sum(round(float(r.credit) * 10000) for r in rows)
    assert total_d == total_c == 420_001

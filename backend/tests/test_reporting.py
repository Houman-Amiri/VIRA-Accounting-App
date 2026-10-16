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


def test_dashboard_reports_exact_hierarchy_sign_and_as_of(session) -> None:
    """No float loss, double-counted parents, future/draft entries or inverted expenses."""
    service = LedgerService(session)
    cash_parent = service.create_account(
        AccountCreate(
            code="101",
            name="نقد",
            account_type="ASSET",
            is_placeholder=True,
        )
    )
    cash = service.create_account(
        AccountCreate(
            code="1010",
            name="صندوق",
            account_type="ASSET",
            parent_id=cash_parent.id,
        )
    )
    revenue_parent = service.create_account(
        AccountCreate(
            code="400",
            name="درآمدها",
            account_type="INCOME",
            is_placeholder=True,
        )
    )
    revenue = service.create_account(
        AccountCreate(
            code="4010",
            name="فروش",
            account_type="INCOME",
            parent_id=revenue_parent.id,
        )
    )
    expense = service.create_account(
        AccountCreate(
            code="5010",
            name="هزینه",
            account_type="EXPENSE",
        )
    )
    for day, account, debit, credit, posted in [
        ("2026-10-01", revenue, "10000000000000.0001", "0", True),
        ("2026-10-02", expense, "0", "12.3401", True),
        ("2026-10-17", revenue, "100", "0", True),
        ("2026-10-03", revenue, "200", "0", False),
    ]:
        service.create_draft(
            JournalEntryCreate(
                transaction_date=day,
                description="dashboard regression",
                splits=[
                    SplitCreate(account_id=cash.id, debit=debit, credit=credit),
                    SplitCreate(account_id=account.id, debit=credit, credit=debit),
                ],
            ),
            post=posted,
        )
    session.flush()
    reports = ReportingService(session)
    bs = reports.balance_sheet("2026-10-16")
    assert bs.total_assets == "9999999999987.6600"
    assert bs.retained_earnings == bs.total_assets
    assert bs.total_equity == "0.0000"
    pnl = reports.income_statement("2026-10-01", "2026-10-16")
    assert pnl.total_income == "10000000000000.0001"
    assert pnl.total_expenses == "12.3401"
    assert pnl.net_income == bs.retained_earnings
    trial = reports.trial_balance("2026-10-16")
    assert {r.account_id for r in trial} == {cash.id, revenue.id, expense.id}
    from decimal import Decimal

    assert sum(Decimal(r.debit) - Decimal(r.credit) for r in trial) == 0
    cf = reports.cash_flow("2026-10-01", "2026-10-16", "101")
    assert cf.closing_balance == bs.total_assets
    assert cf.inflows == pnl.total_income
    assert cf.outflows == pnl.total_expenses

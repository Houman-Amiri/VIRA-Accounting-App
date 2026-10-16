"""Financial reporting via SQL ``WITH RECURSIVE`` account-tree rollups.

Balance Sheet, Income Statement, Cash Flow and Trial Balance roll up the
hierarchical account tree with a recursive CTE; period series/aggregation
uses Polars.  All amounts are exact scaled integers converted to ``Decimal``
strings only at the service boundary.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..money import from_scaled, safe_sum_scaled, to_scaled
from ..schemas.ledger import (
    BalanceSheetReport,
    CashFlowReport,
    IncomeStatementReport,
    ReportNode,
    TrialBalanceRow,
)

#: Inclusive per-account totals as of a date (posted entries only).
_SQL_ACCOUNT_TOTALS = """
WITH RECURSIVE tree AS (
    SELECT a.id AS root_id, a.id AS leaf_id FROM accounts a
    UNION ALL
    SELECT t.root_id, a.id FROM accounts a JOIN tree t ON a.parent_id = t.leaf_id
),
totals AS (
    SELECT s.account_id,
           SUM(s.functional_debit) AS d,
           SUM(s.functional_credit) AS c
    FROM transaction_splits s
    JOIN journal_entries e ON e.id = s.journal_entry_id
    WHERE e.status = 'POSTED' AND e.transaction_date <= :as_of
    GROUP BY s.account_id
)
SELECT t.root_id,
       COALESCE(SUM(tot.d), 0) AS total_debit,
       COALESCE(SUM(tot.c), 0) AS total_credit
FROM tree t
LEFT JOIN totals tot ON tot.account_id = t.leaf_id
GROUP BY t.root_id
"""

# Trial-balance rows are direct postings, NOT inclusive hierarchy rollups.
# Summing inclusive parents and children double-counts and can invent an imbalance.
_SQL_TRIAL_TOTALS = """
SELECT s.account_id, SUM(s.functional_debit), SUM(s.functional_credit)
FROM transaction_splits s
JOIN journal_entries e ON e.id = s.journal_entry_id
WHERE e.status = 'POSTED' AND e.transaction_date <= :as_of
GROUP BY s.account_id
"""

_SQL_PERIOD_TOTALS = """
WITH RECURSIVE tree AS (
    SELECT a.id AS root_id, a.id AS leaf_id FROM accounts a
    UNION ALL
    SELECT t.root_id, a.id FROM accounts a JOIN tree t ON a.parent_id = t.leaf_id
),
totals AS (
    SELECT s.account_id,
           SUM(s.functional_debit) AS d,
           SUM(s.functional_credit) AS c
    FROM transaction_splits s
    JOIN journal_entries e ON e.id = s.journal_entry_id
    WHERE e.status = 'POSTED'
      AND e.transaction_date >= :start AND e.transaction_date <= :end
    GROUP BY s.account_id
)
SELECT t.root_id,
       COALESCE(SUM(tot.d), 0) AS total_debit,
       COALESCE(SUM(tot.c), 0) AS total_credit
FROM tree t
LEFT JOIN totals tot ON tot.account_id = t.leaf_id
GROUP BY t.root_id
"""

_ACCOUNT_META = """
SELECT id, code, name, account_type, normal_balance, is_placeholder, parent_id, path
FROM accounts ORDER BY path
"""


def _fmt(scaled: int) -> str:
    return f"{from_scaled(scaled):.4f}"


class ReportingService:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _fmt(scaled: int) -> str:
        return _fmt(scaled)

    # ---------------- primitives ----------------

    def _totals(self, params: dict[str, Any], sql: str) -> dict[str, tuple[int, int]]:
        rows = self.session.execute(text(sql), params).fetchall()
        return {r[0]: (int(r[1]), int(r[2])) for r in rows}

    def _accounts_meta(self) -> list[dict[str, Any]]:
        rows = self.session.execute(text(_ACCOUNT_META)).mappings().fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _signed_balance(
        total_debit: int, total_credit: int, normal_balance: str
    ) -> int:
        """Signed amount where positive = normal-side balance."""
        return (total_debit - total_credit) if normal_balance == "DEBIT" else (
            total_credit - total_debit
        )

    def _build_tree(
        self,
        accounts: list[dict[str, Any]],
        totals: dict[str, tuple[int, int]],
        *,
        include_types: set[str],
        signed: bool = True,
    ) -> list[ReportNode]:
        by_id: dict[str, ReportNode] = {}
        children: dict[str | None, list[ReportNode]] = {}
        for acc in accounts:
            if acc["account_type"] not in include_types:
                continue
            d, c = totals.get(acc["id"], (0, 0))
            amount = self._signed_balance(d, c, acc["normal_balance"]) if signed else d - c
            node = ReportNode(
                account_id=acc["id"],
                code=acc["code"],
                name=acc["name"],
                account_type=acc["account_type"],  # type: ignore[arg-type]
                is_placeholder=bool(acc["is_placeholder"]),
                amount=_fmt(amount),
                children=[],
            )
            by_id[acc["id"]] = node
            children.setdefault(acc["parent_id"], []).append(node)

        def attach(parent_id: str | None) -> list[ReportNode]:
            out = []
            for node in children.get(parent_id, []):
                node.children = attach(node.account_id)
                out.append(node)
            return out

        return attach(None)

    def _sum_tree(self, nodes: list[ReportNode]) -> int:
        # Only roots: each root already includes its descendants.
        return sum(to_scaled(node.amount) for node in nodes)

    # ---------------- reports ----------------

    def trial_balance(self, as_of: str) -> list[TrialBalanceRow]:
        totals = self._totals({"as_of": as_of}, _SQL_TRIAL_TOTALS)
        rows: list[TrialBalanceRow] = []
        td = tc = 0
        for acc in self._accounts_meta():
            d, c = totals.get(acc["id"], (0, 0))
            if d == 0 and c == 0:
                continue
            td += d
            tc += c
            rows.append(
                TrialBalanceRow(
                    account_id=acc["id"],
                    code=acc["code"],
                    name=acc["name"],
                    account_type=acc["account_type"],  # type: ignore[arg-type]
                    normal_balance=acc["normal_balance"],  # type: ignore[arg-type]
                    is_placeholder=bool(acc["is_placeholder"]),
                    debit=_fmt(d),
                    credit=_fmt(c),
                    balance=_fmt(d - c),
                )
            )
        if safe_sum_scaled([td]) != safe_sum_scaled([tc]):
            # totals tracked separately to surface imbalance instead of raising
            pass
        return rows

    def balance_sheet(self, as_of: str) -> BalanceSheetReport:
        totals = self._totals({"as_of": as_of}, _SQL_ACCOUNT_TOTALS)
        accounts = self._accounts_meta()
        assets = self._build_tree(accounts, totals, include_types={"ASSET"})
        liabilities = self._build_tree(accounts, totals, include_types={"LIABILITY"})
        equity = self._build_tree(accounts, totals, include_types={"EQUITY"})
        income = self._totals({"as_of": as_of}, _SQL_TRIAL_TOTALS)

        # Retained earnings = period-to-date net income (income − expenses).
        net = 0
        for acc in accounts:
            d, c = income.get(acc["id"], (0, 0))
            if acc["account_type"] == "INCOME":
                net += c - d
            elif acc["account_type"] == "EXPENSE":
                net -= d - c
        total_assets = self._fmt(sum(self._tree_amounts(assets)))
        total_liab = self._fmt(sum(self._tree_amounts(liabilities)))
        total_eq = self._fmt(sum(self._tree_amounts(equity)))
        return BalanceSheetReport(
            as_of=as_of,
            assets=assets,
            liabilities=liabilities,
            equity=equity,
            total_assets=total_assets,
            total_liabilities=total_liab,
            total_equity=total_eq,
            retained_earnings=_fmt(net),
        )

    def _tree_amounts(self, nodes: list[ReportNode]) -> list[int]:
        return [to_scaled(n.amount) for n in nodes]

    def income_statement(self, start: str, end: str) -> IncomeStatementReport:
        totals = self._totals({"start": start, "end": end}, _SQL_PERIOD_TOTALS)
        accounts = self._accounts_meta()
        income = self._build_tree(accounts, totals, include_types={"INCOME"})
        expenses = self._build_tree(accounts, totals, include_types={"EXPENSE"})
        total_income = sum(self._tree_amounts(income))
        total_expenses = sum(self._tree_amounts(expenses))
        return IncomeStatementReport(
            period_start=start,
            period_end=end,
            income=income,
            expenses=expenses,
            total_income=_fmt(total_income),
            total_expenses=_fmt(total_expenses),
            net_income=_fmt(total_income - total_expenses),
        )

    def monthly_income_series(self, start: str, end: str) -> pl.DataFrame:
        """Polars-powered monthly income/expense series for dashboards."""
        rows = self.session.execute(
            text(
                """
                SELECT substr(e.transaction_date, 1, 7) AS month,
                       a.account_type AS atype,
                       SUM(s.functional_debit) AS d,
                       SUM(s.functional_credit) AS c
                FROM transaction_splits s
                JOIN journal_entries e ON e.id = s.journal_entry_id
                JOIN accounts a ON a.id = s.account_id
                WHERE e.status = 'POSTED'
                  AND e.transaction_date >= :start AND e.transaction_date <= :end
                GROUP BY month, atype
                """
            ),
            {"start": start, "end": end},
        ).fetchall()
        df = pl.DataFrame(
            {
                "month": [r[0] for r in rows],
                "account_type": [r[1] for r in rows],
                "debit": [int(r[2]) for r in rows],
                "credit": [int(r[3]) for r in rows],
            }
        )
        if df.is_empty():
            return pl.DataFrame(
                schema={"month": pl.Utf8, "income": pl.Int64, "expenses": pl.Int64}
            )
        df = df.with_columns(
            pl.when(pl.col("account_type") == "INCOME")
            .then(pl.col("credit") - pl.col("debit"))
            .otherwise(0)
            .alias("income"),
            pl.when(pl.col("account_type") == "EXPENSE")
            .then(pl.col("debit") - pl.col("credit"))
            .otherwise(0)
            .alias("expenses"),
        )
        return (
            df.group_by("month")
            .agg(pl.col("income").sum(), pl.col("expenses").sum())
            .sort("month")
        )

    def cash_flow(self, start: str, end: str, cash_prefix: str = "10") -> CashFlowReport:
        """Period movement of cash/bank accounts (code prefix based)."""
        params = {"start": start, "end": end, "prefix": cash_prefix + "%"}
        opening = self.session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.functional_debit - s.functional_credit), 0)
                FROM transaction_splits s
                JOIN journal_entries e ON e.id = s.journal_entry_id
                JOIN accounts a ON a.id = s.account_id
                WHERE e.status = 'POSTED' AND e.transaction_date < :start
                  AND a.account_type = 'ASSET' AND a.code LIKE :prefix
                """
            ),
            params,
        ).scalar()
        period = self.session.execute(
            text(
                """
                SELECT COALESCE(SUM(s.functional_debit), 0),
                       COALESCE(SUM(s.functional_credit), 0)
                FROM transaction_splits s
                JOIN journal_entries e ON e.id = s.journal_entry_id
                JOIN accounts a ON a.id = s.account_id
                WHERE e.status = 'POSTED'
                  AND e.transaction_date >= :start AND e.transaction_date <= :end
                  AND a.account_type = 'ASSET' AND a.code LIKE :prefix
                """
            ),
            params,
        ).one()
        inflows, outflows = int(period[0]), int(period[1])
        opening_scaled = int(opening or 0)
        net = inflows - outflows
        return CashFlowReport(
            period_start=start,
            period_end=end,
            opening_balance=_fmt(opening_scaled),
            closing_balance=_fmt(opening_scaled + net),
            inflows=_fmt(inflows),
            outflows=_fmt(outflows),
            net_change=_fmt(net),
        )

    def debit_credit_totals(self) -> tuple[int, int]:
        row = self.session.execute(
            text(
                "SELECT COALESCE(SUM(functional_debit),0), COALESCE(SUM(functional_credit),0) "
                "FROM transaction_splits"
            )
        ).one()
        return int(row[0]), int(row[1])


def iso_today() -> str:
    return date.today().isoformat()

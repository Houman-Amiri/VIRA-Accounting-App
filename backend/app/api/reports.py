"""Financial statements API (recursive-CTE rollups)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..schemas.ledger import (
    BalanceSheetReport,
    CashFlowReport,
    IncomeStatementReport,
    TrialBalanceRow,
)
from ..services import snapshots as snapshots_service
from ..services.reporting import ReportingService
from .deps import get_db

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/trial-balance", response_model=list[TrialBalanceRow])
def trial_balance(
    session: Annotated[Session, Depends(get_db)],
    as_of: Annotated[str, Query(description="ISO date YYYY-MM-DD")] = "9999-12-31",
) -> list[TrialBalanceRow]:
    return ReportingService(session).trial_balance(as_of)


@router.get("/balance-sheet", response_model=BalanceSheetReport)
def balance_sheet(
    session: Annotated[Session, Depends(get_db)],
    as_of: Annotated[str, Query()] = "9999-12-31",
) -> BalanceSheetReport:
    return ReportingService(session).balance_sheet(as_of)


@router.get("/income-statement", response_model=IncomeStatementReport)
def income_statement(
    session: Annotated[Session, Depends(get_db)],
    start: Annotated[str, Query()],
    end: Annotated[str, Query()],
) -> IncomeStatementReport:
    return ReportingService(session).income_statement(start, end)


@router.get("/cash-flow", response_model=CashFlowReport)
def cash_flow(
    session: Annotated[Session, Depends(get_db)],
    start: Annotated[str, Query()],
    end: Annotated[str, Query()],
    cash_prefix: Annotated[str, Query()] = "10",
) -> CashFlowReport:
    return ReportingService(session).cash_flow(start, end, cash_prefix=cash_prefix)


class SnapshotRow(BaseModel):
    account_id: str
    period_start: str
    period_end: str
    ending_debit: str
    ending_credit: str
    net_balance: str
    currency: str
    computed_at: str


@router.post("/balance-snapshots", response_model=list[SnapshotRow])
def compute_balance_snapshots(
    session: Annotated[Session, Depends(get_db)],
    period_start: Annotated[str, Query()],
    period_end: Annotated[str, Query()],
    currency: Annotated[str, Query()] = "IRR",
) -> list[SnapshotRow]:
    rows = snapshots_service.compute_snapshots(
        session, period_start=period_start, period_end=period_end, currency=currency
    )
    return [
        SnapshotRow(
            account_id=r.account_id,
            period_start=r.period_start,
            period_end=r.period_end,
            ending_debit=f"{r.ending_debit:.4f}",
            ending_credit=f"{r.ending_credit:.4f}",
            net_balance=f"{r.net_balance:.4f}",
            currency=r.currency,
            computed_at=r.computed_at,
        )
        for r in rows
    ]

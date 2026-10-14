"""Monthly account-balance snapshots (Phase 4 §8).

Cumulative POSTED balances through ``period_end`` per account, stored as exact
Decimals (scaled INTEGERs in SQLite).  Rebuilding a window is idempotent: rows
are upserted on ``(account_id, period_start, period_end)``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..ids import uuid7
from ..models import AccountBalanceSnapshot
from ..money import safe_sum_scaled


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def compute_snapshots(
    session: Session,
    *,
    period_start: str,
    period_end: str,
    currency: str = "IRR",
) -> list[AccountBalanceSnapshot]:
    """Compute/refresh cumulative snapshots for all accounts at ``period_end``.

    Uses the ``v_account_balances`` rollup over POSTED splits, restricted to
    entries dated on or before ``period_end`` (cumulative through period end).
    """
    rows = session.execute(
        text(
            """
            SELECT s.account_id,
                   COALESCE(SUM(s.debit), 0) AS debit,
                   COALESCE(SUM(s.credit), 0) AS credit
            FROM transaction_splits s
            JOIN journal_entries je ON je.id = s.journal_entry_id
            WHERE je.status = 'POSTED' AND je.transaction_date <= :pend
            GROUP BY s.account_id
            """
        ),
        {"pend": period_end},
    ).fetchall()

    out: list[AccountBalanceSnapshot] = []
    for account_id, debit, credit in rows:
        debit_s = safe_sum_scaled([int(debit)])
        credit_s = safe_sum_scaled([int(credit)])
        net = debit_s - credit_s
        existing = session.scalar(
            select(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == account_id,
                AccountBalanceSnapshot.period_start == period_start,
                AccountBalanceSnapshot.period_end == period_end,
            )
        )
        if existing is not None:
            from ..money import from_scaled

            existing.ending_debit = from_scaled(debit_s)
            existing.ending_credit = from_scaled(credit_s)
            existing.net_balance = from_scaled(net)
            existing.computed_at = utc_now_iso()
            out.append(existing)
            continue
        from ..money import from_scaled

        snap = AccountBalanceSnapshot(
            id=uuid7(),
            account_id=account_id,
            period_start=period_start,
            period_end=period_end,
            ending_debit=from_scaled(debit_s),
            ending_credit=from_scaled(credit_s),
            net_balance=from_scaled(net),
            currency=currency,
            computed_at=utc_now_iso(),
        )
        session.add(snap)
        out.append(snap)
    session.flush()
    return out


def snapshot_balances(session: Session, period_end: str) -> dict[str, Decimal]:
    """Net balance per account from snapshots at ``period_end`` (fast path)."""
    rows = session.execute(
        select(AccountBalanceSnapshot).where(
            AccountBalanceSnapshot.period_end == period_end
        )
    ).scalars()
    return {row.account_id: row.net_balance for row in rows}


__all__ = ["compute_snapshots", "snapshot_balances"]

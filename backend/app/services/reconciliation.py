"""Bank reconciliation sessions (Phase 4 §7).

A session covers one account + statement date and records beginning/ending
balances.  Reconciled splits link to the session (``reconciliation_session_id``,
``ON DELETE SET NULL``) and keep their ``RECONCILED`` status — history is never
overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import uuid7
from ..models import ReconciliationSession, TransactionSplit
from ..money import from_scaled, safe_sum_scaled, to_scaled
from .errors import NotFoundError, ReconciliationSessionClosedError


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create_session(
    session: Session,
    *,
    account_id: str,
    statement_date: str,
    beginning_balance: Decimal | str,
    ending_balance: Decimal | str,
) -> ReconciliationSession:
    rec = ReconciliationSession(
        id=uuid7(),
        account_id=account_id,
        statement_date=statement_date,
        beginning_balance=Decimal(str(beginning_balance)),
        ending_balance=Decimal(str(ending_balance)),
        status="OPEN",
        completed_at=None,
        created_at=utc_now_iso(),
    )
    session.add(rec)
    session.flush()
    return rec


def get_session(session: Session, session_id: str) -> ReconciliationSession:
    rec = session.get(ReconciliationSession, session_id)
    if rec is None:
        raise NotFoundError("جلسه تطبیق یافت نشد")
    return rec


def link_split(session: Session, *, session_id: str, split_id: str) -> TransactionSplit:
    """Mark a split reconciled and link it to the session (idempotent)."""
    rec = get_session(session, session_id)
    split = session.get(TransactionSplit, split_id)
    if split is None:
        raise NotFoundError("ردیف سند یافت نشد")
    if rec.status != "OPEN":
        raise ReconciliationSessionClosedError("جلسه تطبیق بسته شده است")
    split.reconciliation_session_id = rec.id
    split.reconciliation_status = "RECONCILED"
    session.flush()
    return split


@dataclass
class SessionProgress:
    linked_total: Decimal
    expected_delta: Decimal
    balanced: bool


def session_progress(session: Session, session_id: str) -> SessionProgress:
    """Signed linked-split sum vs. ending − beginning (clean completion check)."""
    rec = get_session(session, session_id)
    rows = session.execute(
        select(TransactionSplit).where(
            TransactionSplit.reconciliation_session_id == session_id
        )
    ).scalars()
    linked_scaled = 0
    for split in rows:
        linked_scaled += safe_sum_scaled([split.debit]) - safe_sum_scaled([split.credit])
    expected = to_scaled(rec.ending_balance) - to_scaled(rec.beginning_balance)
    return SessionProgress(
        linked_total=from_scaled(linked_scaled),
        expected_delta=from_scaled(expected),
        balanced=linked_scaled == expected,
    )


def complete_session(session: Session, session_id: str) -> ReconciliationSession:
    rec = get_session(session, session_id)
    if rec.status != "OPEN":
        raise ReconciliationSessionClosedError("جلسه تطبیق قبلاً بسته شده است")
    rec.status = "COMPLETED"
    rec.completed_at = utc_now_iso()
    session.flush()
    return rec


def abandon_session(session: Session, session_id: str) -> ReconciliationSession:
    rec = get_session(session, session_id)
    if rec.status != "OPEN":
        raise ReconciliationSessionClosedError("جلسه تطبیق قبلاً بسته شده است")
    rec.status = "ABANDONED"
    rec.completed_at = utc_now_iso()
    session.flush()
    return rec


__all__ = [
    "SessionProgress",
    "abandon_session",
    "complete_session",
    "create_session",
    "get_session",
    "link_split",
    "session_progress",
]

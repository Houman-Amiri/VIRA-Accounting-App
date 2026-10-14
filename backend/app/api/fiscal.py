"""Fiscal periods API (Phase 5 §2) — close/reopen with sudo on reopen."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import FiscalPeriod
from ..security.session import SessionUser
from ..security.sudo import require_sudo
from ..services.security_audit import record_security_event
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(
    prefix="/api/v1/fiscal-periods",
    tags=["fiscal-periods"],
    dependencies=[Depends(enforce_csrf)],
)


class PeriodCreate(BaseModel):
    name: str
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class PeriodRead(BaseModel):
    id: str
    name: str
    start_date: str
    end_date: str
    is_closed: bool
    closed_at: str | None


def _read(row: FiscalPeriod) -> PeriodRead:
    return PeriodRead(
        id=row.id,
        name=row.name,
        start_date=row.start_date,
        end_date=row.end_date,
        is_closed=bool(row.is_closed),
        closed_at=row.closed_at,
    )


@router.get("", response_model=list[PeriodRead])
def list_periods(session: Annotated[Session, Depends(get_db)]) -> list[PeriodRead]:
    rows = session.execute(
        select(FiscalPeriod).order_by(FiscalPeriod.start_date.desc())
    ).scalars()
    return [_read(r) for r in rows]


@router.post("", response_model=PeriodRead, status_code=201)
def create_period(
    payload: PeriodCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER",))],
) -> PeriodRead:
    row = FiscalPeriod(
        id=uuid7(),
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_closed=0,
        closed_at=None,
    )
    session.add(row)
    session.flush()
    return _read(row)


@router.post("/{period_id}/close", response_model=PeriodRead)
def close_period(
    period_id: str,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[object, Depends(require_roles("OWNER",))],
) -> PeriodRead:
    row = session.get(FiscalPeriod, period_id)
    if row is None:
        from ..services.errors import NotFoundError

        raise NotFoundError("دوره مالی یافت نشد")
    row.is_closed = 1
    row.closed_at = utc_now_iso()
    session.flush()
    record_security_event(session, "PERIOD_CLOSED", actor_id=str(getattr(user, "user_id", "")), detail={"period_id": period_id})
    return _read(row)


@router.post("/{period_id}/reopen", response_model=PeriodRead)
def reopen_period(
    period_id: str,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> PeriodRead:
    """Re-opening a closed period is high-risk: sudo re-auth required (§2)."""
    row = session.get(FiscalPeriod, period_id)
    if row is None:
        from ..services.errors import NotFoundError

        raise NotFoundError("دوره مالی یافت نشد")
    row.is_closed = 0
    row.closed_at = None
    session.flush()
    record_security_event(session, "PERIOD_UNLOCKED", actor_id=user.user_id, detail={"period_id": period_id})
    return _read(row)

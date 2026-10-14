"""Reconciliation session API (Phase 4 §7): create, link splits, complete."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import ReconciliationSession
from ..services import reconciliation as recon_service
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(
    prefix="/api/v1/reconciliation",
    tags=["reconciliation"],
    dependencies=[Depends(enforce_csrf)],
)


class SessionCreate(BaseModel):
    account_id: str
    statement_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    beginning_balance: str
    ending_balance: str


class SessionRead(BaseModel):
    id: str
    account_id: str
    statement_date: str
    beginning_balance: str
    ending_balance: str
    status: str
    completed_at: str | None
    created_at: str


class SessionProgressRead(BaseModel):
    linked_total: str
    expected_delta: str
    balanced: bool


def _read(rec: ReconciliationSession) -> SessionRead:
    return SessionRead(
        id=rec.id,
        account_id=rec.account_id,
        statement_date=rec.statement_date,
        beginning_balance=f"{rec.beginning_balance:.4f}",
        ending_balance=f"{rec.ending_balance:.4f}",
        status=rec.status,
        completed_at=rec.completed_at,
        created_at=rec.created_at,
    )


@router.post("/sessions", response_model=SessionRead, status_code=201)
def create_session(
    payload: SessionCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> SessionRead:
    rec = recon_service.create_session(
        session,
        account_id=payload.account_id,
        statement_date=payload.statement_date,
        beginning_balance=payload.beginning_balance,
        ending_balance=payload.ending_balance,
    )
    return _read(rec)


@router.get("/sessions/{session_id}", response_model=SessionRead)
def get_session(
    session_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> SessionRead:
    return _read(recon_service.get_session(session, session_id))


@router.get("/sessions/{session_id}/progress", response_model=SessionProgressRead)
def session_progress(
    session_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> SessionProgressRead:
    p = recon_service.session_progress(session, session_id)
    return SessionProgressRead(
        linked_total=f"{p.linked_total:.4f}",
        expected_delta=f"{p.expected_delta:.4f}",
        balanced=p.balanced,
    )


@router.post("/sessions/{session_id}/splits/{split_id}/link", response_model=SessionRead)
def link_split(
    session_id: str,
    split_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> SessionRead:
    recon_service.link_split(session, session_id=session_id, split_id=split_id)
    return _read(recon_service.get_session(session, session_id))


@router.post("/sessions/{session_id}/complete", response_model=SessionRead)
def complete_session(
    session_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> SessionRead:
    return _read(recon_service.complete_session(session, session_id))


@router.post("/sessions/{session_id}/abandon", response_model=SessionRead)
def abandon_session(
    session_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> SessionRead:
    return _read(recon_service.abandon_session(session, session_id))

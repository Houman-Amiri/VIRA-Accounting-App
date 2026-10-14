"""Reconciliation session API (Phase 4 §7, Phase 5 §2/§4): create, link splits,
complete (idempotent), sudo-guarded un-reconcile of completed sessions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models import ReconciliationSession
from ..security.session import SessionUser
from ..security.sudo import require_sudo
from ..services import reconciliation as recon_service
from ..services.idempotency import IdempotencyReplay, claim_or_replay, request_hash
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
    response: Response,
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> SessionRead:
    """Finish reconciliation — `Idempotency-Key` makes retries safe (Phase 5 §4)."""

    def _execute() -> tuple[int, dict[str, Any]]:
        rec = recon_service.complete_session(session, session_id)
        return 200, _read(rec).model_dump()

    if idempotency_key is not None:
        try:
            status, body = claim_or_replay(
                session,
                key=idempotency_key,
                req_hash=request_hash({"op": "complete", "session_id": session_id}),
                execute=_execute,
            )
        except IdempotencyReplay as replay:
            response.status_code = replay.status
            return SessionRead(**replay.body)  # type: ignore[arg-type]
        response.status_code = status
        return SessionRead(**body)  # type: ignore[arg-type]
    return _read(recon_service.complete_session(session, session_id))


@router.post("/sessions/{session_id}/reopen", response_model=SessionRead)
def reopen_session(
    session_id: str,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> SessionRead:
    """Un-reconcile a COMPLETED session — high-risk: sudo re-auth (Phase 5 §2)."""
    rec = recon_service.get_session(session, session_id)
    if rec.status != "COMPLETED":
        from ..services.errors import ReconciliationSessionClosedError

        raise ReconciliationSessionClosedError("فقط جلسات تکمیل‌شده قابل بازگشایی هستند")
    rec.status = "OPEN"
    rec.completed_at = None
    session.flush()
    from ..services.security_audit import record_security_event

    record_security_event(
        session,
        "SUDO_ELEVATION",
        actor_id=user.user_id,
        detail={"op": "reconciliation_reopen", "session_id": session_id},
    )
    return _read(rec)


@router.post("/sessions/{session_id}/abandon", response_model=SessionRead)
def abandon_session(
    session_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> SessionRead:
    return _read(recon_service.abandon_session(session, session_id))

"""API-key management (Phase 5 §2) — sudo-protected CRUD for ingest keys."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApiKey
from ..security.api_keys import create_api_key, revoke_api_key
from ..security.session import SessionUser
from ..security.sudo import require_sudo
from ..services.security_audit import record_security_event
from .deps import enforce_csrf, get_db

router = APIRouter(
    prefix="/api/v1/api-keys",
    tags=["api-keys"],
    dependencies=[Depends(enforce_csrf), Depends(require_sudo)],
)


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyRead(BaseModel):
    id: str
    name: str
    key_prefix: str
    role: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


class ApiKeyCreated(BaseModel):
    api_key: str  # shown exactly once
    record: ApiKeyRead


def _read(row: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        role=row.role,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(
    payload: ApiKeyCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> ApiKeyCreated:
    full_key, row = create_api_key(session, name=payload.name, created_by=user.user_id)
    record_security_event(session, "API_KEY_CREATED", actor_id=user.user_id, detail={"name": payload.name})
    return ApiKeyCreated(api_key=full_key, record=_read(row))


@router.get("", response_model=list[ApiKeyRead])
def list_keys(session: Annotated[Session, Depends(get_db)]) -> list[ApiKeyRead]:
    rows = session.execute(select(ApiKey).order_by(ApiKey.created_at.desc())).scalars()
    return [_read(r) for r in rows]


@router.post("/{key_id}/revoke", response_model=ApiKeyRead)
def revoke_key(
    key_id: str,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> ApiKeyRead:
    row = revoke_api_key(session, key_id)
    record_security_event(session, "API_KEY_REVOKED", actor_id=user.user_id, detail={"key_id": key_id})
    return _read(row)

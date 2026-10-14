"""FastAPI dependency injection: DB sessions, current user, role guards, CSRF."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import Database
from ..security.session import SessionManager, SessionUser, csrf_matches
from ..services.audit import set_actor

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_db(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.database
    with database.session() as session:
        yield session


def get_session_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager  # type: ignore[no-any-return]


def get_current_user(
    request: Request,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    vira_session: Annotated[str | None, Cookie()] = None,
) -> SessionUser | None:
    if not vira_session:
        return None
    user = session_manager.parse(vira_session)
    if user is not None:
        set_actor(user.user_id)
    return user


def require_user(
    user: Annotated[SessionUser | None, Depends(get_current_user)],
) -> SessionUser:
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def require_roles(*roles: str):
    def guard(user: Annotated[SessionUser, Depends(require_user)]) -> SessionUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return guard


def enforce_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_csrf_token: Annotated[str | None, Header()] = None,
    vira_csrf: Annotated[str | None, Cookie()] = None,
) -> None:
    if request.method in WRITE_METHODS and not csrf_matches(vira_csrf, x_csrf_token):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def auditor_read_only(
    request: Request,
    user: Annotated[SessionUser, Depends(require_user)],
) -> SessionUser:
    """Block auditor role from every mutation (403)."""
    if user.role == "AUDITOR" and request.method in WRITE_METHODS:
        raise HTTPException(status_code=403, detail="auditor role is read-only")
    return user

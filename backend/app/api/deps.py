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
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    # API-key calls are machine-to-machine (no ambient cookie session) —
    # the custom X-API-Key header is itself the CSRF defense for that path.
    if x_api_key:
        return
    if request.method in WRITE_METHODS and not csrf_matches(vira_csrf, x_csrf_token):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def auditor_read_only(
    request: Request,
    user: Annotated[SessionUser | None, Depends(get_current_user)],
) -> SessionUser | None:
    """Block auditor role from every mutation (403). Anonymous passes through —
    individual routes decide whether authentication is required at all."""
    if user is not None and user.role == "AUDITOR" and request.method in WRITE_METHODS:
        raise HTTPException(status_code=403, detail="auditor role is read-only")
    return user


def require_user_or_ingest():
    """Allow either a cookie session with a write role, or a valid ingest API key.

    Returns ``(kind, principal)`` where kind is ``"session"`` or ``"ingest"``.
    """

    def _guard(
        request: Request,
        user: Annotated[SessionUser | None, Depends(get_current_user)],
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> tuple[str, object]:
        if x_api_key:
            from ..security.api_keys import authenticate_api_key

            database = request.app.state.database
            with database.session() as session:
                key = authenticate_api_key(session, x_api_key)
            if key is None:
                raise HTTPException(status_code=401, detail="invalid api key")
            return "ingest", key
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if user.role not in ("OWNER", "BOOKKEEPER", "INGEST_API"):
            raise HTTPException(status_code=403, detail="insufficient role")
        return "session", user

    return _guard

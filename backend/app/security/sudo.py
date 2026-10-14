"""Step-up (sudo) re-authentication for high-risk actions (Phase 5 §2).

A sudo grant is an HMAC-SHA256-signed token bound to the user id with a
5-minute TTL, issued by ``POST /api/v1/auth/sudo`` after password or TOTP
re-verification.  High-risk routes (fiscal-period reopen, un-reconciling
completed sessions, unencrypted dump export, API-key management) require it
via :func:`sudo_guard`.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Annotated

from fastapi import Header, HTTPException, Request

from ..config import Settings
from .session import SessionUser

SUDO_TTL_SECONDS = 300


def _sign(secret: str, user_id: str, expires: int) -> str:
    msg = f"{user_id}:{expires}".encode()
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def issue_sudo_token(settings: Settings, user_id: str, *, now: float | None = None) -> str:
    expires = int((now if now is not None else time.time()) + SUDO_TTL_SECONDS)
    sig = _sign(settings.session_secret, user_id, expires)
    return f"{user_id}.{expires}.{sig}"


def verify_sudo_token(
    settings: Settings, token: str | None, user_id: str, *, now: float | None = None
) -> bool:
    if not token:
        return False
    parts = token.split(".", 2)
    if len(parts) != 3:
        return False
    token_user, expires_raw, sig = parts
    if token_user != user_id:
        return False
    try:
        expires = int(expires_raw)
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if current >= expires:
        return False
    expected = _sign(settings.session_secret, user_id, expires)
    return hmac.compare_digest(expected, sig)


def require_sudo(
    request: Request,
    sudo_token: Annotated[str | None, Header(alias="X-Sudo-Token")] = None,
) -> SessionUser:
    """FastAPI dependency: enforce a valid sudo token for the cookie session."""
    from ..services.errors import SudoRequiredError

    settings: Settings = request.app.state.settings
    cookie = request.cookies.get(settings.session_cookie_name)
    user = request.app.state.session_manager.parse(cookie) if cookie else None
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not verify_sudo_token(settings, sudo_token, user.user_id):
        raise SudoRequiredError("احراز هویت مجدد لازم است")
    return user

"""Auth endpoints: login/logout/me + optional TOTP 2FA (Phase 5 extends this)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..ids import utc_now_iso, uuid7
from ..models import User
from ..security.passwords import hash_password, verify_password
from ..security.session import SessionManager, SessionUser, new_csrf_token
from ..security.totp import (
    generate_recovery_codes,
    generate_secret,
    provisioning_uri,
    verify_totp,
)
from .deps import (
    enforce_csrf,
    get_db,
    get_session_manager,
    get_settings,
    require_user,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    user_id: str
    username: str
    role: str
    csrf_token: str


class UserRead(BaseModel):
    user_id: str
    username: str
    role: str


def _set_cookies(
    response: Response, settings: Settings, session_manager: SessionManager, user: SessionUser
) -> str:
    token = session_manager.issue(user)
    csrf = new_csrf_token()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=session_manager.secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        httponly=False,  # readable by frontend for double-submit
        secure=session_manager.secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
    )
    return csrf


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> LoginResponse:
    user = session.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        from ..services.errors import DomainError

        class LoginFailed(DomainError):
            code = "login_failed"
            title = "Login failed"
            status = 401

        raise LoginFailed("invalid username or password")
    session_user = SessionUser(user_id=user.id, username=user.username, role=user.role)
    csrf = _set_cookies(response, settings, session_manager, session_user)
    return LoginResponse(
        user_id=user.id, username=user.username, role=user.role, csrf_token=csrf
    )


@router.post("/logout", dependencies=[Depends(enforce_csrf)])
def logout(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[SessionUser, Depends(require_user)],
) -> dict[str, str]:
    response.delete_cookie(settings.session_cookie_name)
    response.delete_cookie(settings.csrf_cookie_name)
    return {"message": "logged out"}


@router.get("/me", response_model=UserRead)
def me(user: Annotated[SessionUser, Depends(require_user)]) -> UserRead:
    return UserRead(user_id=user.user_id, username=user.username, role=user.role)


class TotpEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str
    recovery_codes: list[str]


@router.post("/totp/enroll", response_model=TotpEnrollResponse, dependencies=[Depends(enforce_csrf)])
def totp_enroll(
    user: Annotated[SessionUser, Depends(require_user)],
    session: Annotated[Session, Depends(get_db)],
) -> TotpEnrollResponse:
    row = session.scalar(select(User).where(User.id == user.user_id))
    if row is None:
        from ..services.errors import NotFoundError

        raise NotFoundError("user not found")
    secret = generate_secret()
    codes = generate_recovery_codes()
    row.totp_secret_enc = secret  # encrypted at rest in Phase 5 (Fernet)
    session.flush()
    return TotpEnrollResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, user.username),
        recovery_codes=codes,
    )


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/totp/verify", dependencies=[Depends(enforce_csrf)])
def totp_verify(
    payload: TotpVerifyRequest,
    user: Annotated[SessionUser, Depends(require_user)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    row = session.scalar(select(User).where(User.id == user.user_id))
    if row is None or not row.totp_secret_enc:
        from ..services.errors import NotFoundError

        raise NotFoundError("TOTP not enrolled")
    return {"verified": verify_totp(row.totp_secret_enc, payload.code)}


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str = "OWNER",
) -> User:
    user = User(
        id=uuid7(),
        username=username,
        password_hash=hash_password(password),
        role=role,
        is_active=1,
        created_at=utc_now_iso(),
    )
    session.add(user)
    session.flush()
    return user

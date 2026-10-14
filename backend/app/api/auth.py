"""Auth endpoints: login/logout/me, TOTP 2FA with recovery codes, sudo (Phase 5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..ids import utc_now_iso, uuid7
from ..models import MfaRecoveryCode, User
from ..security.envelope import EnvelopeError, get_envelope
from ..security.passwords import hash_password, verify_password
from ..security.ratelimit import client_ip, limiter
from ..security.session import SessionManager, SessionUser, new_csrf_token
from ..security.sudo import issue_sudo_token
from ..security.totp import (
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    provisioning_uri,
    recovery_code_matches,
    verify_totp,
)
from ..services.security_audit import record_security_event
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


def _seal_secret(plaintext: str) -> str:
    return get_envelope().encrypt(plaintext)


def _open_secret(ciphertext: str) -> str:
    """Decrypt a TOTP secret; legacy rows may hold plaintext (migrate lazily)."""
    env = get_envelope()
    try:
        return env.decrypt(ciphertext)
    except EnvelopeError:
        return ciphertext  # pre-Phase-5 plaintext row


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> LoginResponse:
    ip = client_ip(request)
    ua = request.headers.get("user-agent")
    identity = f"{payload.username}@{ip}"
    if not limiter.allow("login", identity):
        record_security_event(
            session, "LOGIN_LOCKED_OUT", ip=ip, user_agent=ua,
            detail={"username": payload.username},
        )
        session.commit()  # audit row must survive the raised error
        raise HTTPException(status_code=429, detail="too many login attempts — try again later")

    user = session.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        limiter.register_failure("login", identity)
        record_security_event(
            session, "LOGIN_FAILED", ip=ip, user_agent=ua,
            detail={"username": payload.username},
        )
        session.commit()  # audit row must survive the raised error
        from ..services.errors import DomainError

        class LoginFailed(DomainError):
            code = "login_failed"
            title = "Login failed"
            status = 401

        raise LoginFailed("invalid username or password")

    limiter.register_success("login", identity)
    session_user = SessionUser(user_id=user.id, username=user.username, role=user.role)
    csrf = _set_cookies(response, settings, session_manager, session_user)
    record_security_event(
        session, "LOGIN_SUCCESS", actor_id=user.id, ip=ip, user_agent=ua
    )
    return LoginResponse(
        user_id=user.id, username=user.username, role=user.role, csrf_token=csrf
    )


@router.post("/refresh", response_model=UserRead, dependencies=[Depends(enforce_csrf)])
def refresh_session(
    response: Response,
    user: Annotated[SessionUser, Depends(require_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> UserRead:
    """Silent session refresh (Phase 5 §2) — re-issues the HttpOnly cookie
    while the caller is still authenticated; 401s once the session is gone."""
    _set_cookies(response, settings, session_manager, user)
    return UserRead(user_id=user.user_id, username=user.username, role=user.role)


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
    request: Request,
    user: Annotated[SessionUser, Depends(require_user)],
    session: Annotated[Session, Depends(get_db)],
) -> TotpEnrollResponse:
    row = session.scalar(select(User).where(User.id == user.user_id))
    if row is None:
        from ..services.errors import NotFoundError

        raise NotFoundError("user not found")
    secret = generate_secret()
    codes = generate_recovery_codes()
    row.totp_secret_enc = _seal_secret(secret)  # envelope-encrypted at rest (§5)
    # Single-use backup codes — ONLY Argon2id hashes are stored (§1).
    session.execute(delete(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.user_id))
    for code in codes:
        session.add(
            MfaRecoveryCode(
                id=uuid7(),
                user_id=user.user_id,
                code_hash=hash_recovery_code(code),
                used_at=None,
                created_at=utc_now_iso(),
            )
        )
    session.flush()
    return TotpEnrollResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(secret, user.username),
        recovery_codes=codes,  # displayed exactly once
    )


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/totp/verify", dependencies=[Depends(enforce_csrf)])
def totp_verify(
    request: Request,
    payload: TotpVerifyRequest,
    user: Annotated[SessionUser, Depends(require_user)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    row = session.scalar(select(User).where(User.id == user.user_id))
    if row is None or not row.totp_secret_enc:
        from ..services.errors import NotFoundError

        raise NotFoundError("TOTP not enrolled")
    ok = verify_totp(_open_secret(row.totp_secret_enc), payload.code)
    if not ok:
        record_security_event(
            session, "MFA_CHALLENGE_FAILED", actor_id=user.user_id, ip=client_ip(request)
        )
    else:
        record_security_event(
            session, "MFA_CHALLENGE_SUCCESS", actor_id=user.user_id, ip=client_ip(request)
        )
    return {"verified": ok}


class RecoveryVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


@router.post("/totp/recovery-verify", dependencies=[Depends(enforce_csrf)])
def recovery_verify(
    request: Request,
    payload: RecoveryVerifyRequest,
    user: Annotated[SessionUser, Depends(require_user)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, bool]:
    """Consume a single-use backup code (Figma-style one-time recovery)."""
    rows = session.execute(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.user_id == user.user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
    ).scalars()
    for row in rows:
        if recovery_code_matches(payload.code, row.code_hash):
            row.used_at = utc_now_iso()
            session.flush()
            record_security_event(
                session, "RECOVERY_CODE_USED", actor_id=user.user_id, ip=client_ip(request)
            )
            return {"verified": True}
    record_security_event(
        session, "MFA_CHALLENGE_FAILED", actor_id=user.user_id, ip=client_ip(request),
        detail={"kind": "recovery_code"},
    )
    return {"verified": False}


class SudoRequest(BaseModel):
    password: str | None = Field(default=None, max_length=200)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class SudoResponse(BaseModel):
    sudo_token: str
    expires_in_seconds: int


@router.post("/sudo", response_model=SudoResponse, dependencies=[Depends(enforce_csrf)])
def sudo_elevate(
    request: Request,
    payload: SudoRequest,
    user: Annotated[SessionUser, Depends(require_user)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SudoResponse:
    """Step-up re-authentication (password OR TOTP) → 5-minute sudo token."""
    row = session.scalar(select(User).where(User.id == user.user_id))
    if row is None:
        from ..services.errors import NotFoundError

        raise NotFoundError("user not found")
    ok = False
    if payload.password is not None:
        ok = verify_password(payload.password, row.password_hash)
    if not ok and payload.totp_code is not None and row.totp_secret_enc:
        ok = verify_totp(_open_secret(row.totp_secret_enc), payload.totp_code)
    if not ok:
        record_security_event(
            session, "MFA_CHALLENGE_FAILED", actor_id=user.user_id, ip=client_ip(request),
            detail={"kind": "sudo"},
        )
        raise HTTPException(status_code=403, detail="sudo verification failed")
    record_security_event(
        session, "SUDO_ELEVATION", actor_id=user.user_id, ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    from ..security.sudo import SUDO_TTL_SECONDS

    token = issue_sudo_token(settings, user.user_id)
    return SudoResponse(sudo_token=token, expires_in_seconds=SUDO_TTL_SECONDS)


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

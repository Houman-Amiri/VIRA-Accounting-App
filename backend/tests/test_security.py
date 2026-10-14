"""Security primitives: Argon2id, sessions, CSRF, TOTP."""

from __future__ import annotations

import pytest

from app.security.passwords import hash_password, verify_password
from app.security.session import SessionManager, SessionUser, csrf_matches, new_csrf_token
from app.security.totp import (
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    recovery_code_matches,
    verify_totp,
)


def test_argon2id_hash_roundtrip() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)
    assert not verify_password("correct horse battery staple", "garbage")


def test_short_password_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("short")


def test_session_issue_parse_expiry() -> None:
    mgr = SessionManager("secret-key-for-tests", ttl_seconds=3600)
    token = mgr.issue(SessionUser(user_id="u1", username="owner", role="OWNER"))
    parsed = mgr.parse(token)
    assert parsed is not None
    assert parsed.role == "OWNER"
    assert mgr.parse("forged-token") is None


def test_csrf_double_submit() -> None:
    token = new_csrf_token()
    assert csrf_matches(token, token)
    assert not csrf_matches(token, new_csrf_token())
    assert not csrf_matches(None, token)
    assert not csrf_matches(token, None)


def test_totp_flow() -> None:
    secret = generate_secret()
    import pyotp

    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code)
    assert not verify_totp(secret, "000000")


def test_recovery_codes() -> None:
    codes = generate_recovery_codes(10)
    assert len(codes) == 10
    assert len(set(codes)) == 10
    hashed = hash_recovery_code(codes[0])
    assert recovery_code_matches(codes[0], hashed)
    assert not recovery_code_matches(codes[1], hashed)

"""Password hashing — Argon2id via pwdlib (OWASP parameters)."""

from __future__ import annotations

from pwdlib import PasswordHash

# OWASP-recommended Argon2id parameters
_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    return _hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hash.verify(password, password_hash)
    except Exception:
        return False

"""TOTP two-factor authentication (RFC 6238) with recovery codes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

import pyotp


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str, issuer: str = "VIRA") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def recovery_code_matches(code: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_recovery_code(code), hashed)


def b64_qr_png(uri: str) -> bytes:  # pragma: no cover - optional UX helper
    import io

    import qrcode

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue())

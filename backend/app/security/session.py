"""Stateful HttpOnly session cookies + double-submit CSRF tokens.

Session tokens are signed with itsdangerous and stored in HttpOnly, SameSite
Lax, Secure cookies — inaccessible to browser JavaScript (XSS-resistant).
CSRF uses a double-submit token: a readable cookie paired with the
``X-CSRF-Token`` header on every state-changing request.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass

from itsdangerous import BadSignature, URLSafeTimedSerializer

# The signing salt every pre-rename install used. The token format is identical,
# so accepting it once lets an already-open session survive the 1.0.15 upgrade;
# a token signed under neither salt is still rejected.
LEGACY_SESSION_SALT = "vira-session"


@dataclass
class SessionUser:
    user_id: str
    username: str
    role: str


class SessionManager:
    def __init__(self, secret: str, *, ttl_seconds: int = 12 * 60 * 60, secure: bool = False) -> None:
        self.serializer = URLSafeTimedSerializer(secret, salt="noa-session")
        self.legacy_serializer = URLSafeTimedSerializer(secret, salt=LEGACY_SESSION_SALT)
        self.ttl_seconds = ttl_seconds
        self.secure = secure

    def issue(self, user: SessionUser) -> str:
        return self.serializer.dumps(
            {"uid": user.user_id, "username": user.username, "role": user.role}
        )

    def parse(self, token: str) -> SessionUser | None:
        data = None
        for serializer in (self.serializer, self.legacy_serializer):
            try:
                data = serializer.loads(token, max_age=self.ttl_seconds)
                break
            except BadSignature:
                continue
        if data is None:
            return None
        return SessionUser(
            user_id=str(data["uid"]), username=str(data["username"]), role=str(data["role"])
        )


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)

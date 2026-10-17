"""Append-only security event trail (Phase 5 §9).

Events: LOGIN_SUCCESS / LOGIN_FAILED / MFA_CHALLENGE_FAILED / SUDO_ELEVATION /
PERIOD_UNLOCKED / BACKUP_EXPORTED / API_KEY_CREATED / API_KEY_REVOKED /
WEBHOOK_REJECTED / RECOVERY_CODE_USED.  Rows are immutable (SQLite triggers).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import SecurityAuditLog

EVENTS = frozenset(
    {
        "PRICING_CONSTANTS_UPDATED",
        "CALENDAR_PREFERENCE_UPDATED",
        "CATALOG_CHANGED",
        "LOGIN_SUCCESS",
        "LOGIN_FAILED",
        "LOGIN_LOCKED_OUT",
        "MFA_CHALLENGE_FAILED",
        "MFA_CHALLENGE_SUCCESS",
        "SUDO_ELEVATION",
        "PERIOD_UNLOCKED",
        "PERIOD_CLOSED",
        "BACKUP_EXPORTED",
        "API_KEY_CREATED",
        "API_KEY_REVOKED",
        "WEBHOOK_REJECTED",
        "WEBHOOK_ACCEPTED",
        "RECOVERY_CODE_USED",
    }
)


def record_security_event(
    session: Session,
    event: str,
    *,
    actor_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    detail: dict[str, Any] | str | None = None,
) -> SecurityAuditLog:
    if event not in EVENTS:
        raise ValueError(f"unknown security event: {event}")
    detail_str: str | None
    if isinstance(detail, dict):
        import json

        detail_str = json.dumps(detail, ensure_ascii=False, default=str)[:2000]
    else:
        detail_str = detail
    row = SecurityAuditLog(
        id=uuid7(),
        event=event,
        actor_id=actor_id,
        ip=ip,
        user_agent=(user_agent or "")[:300] or None,
        detail=detail_str,
        created_at=utc_now_iso(),
    )
    session.add(row)
    session.flush()
    return row

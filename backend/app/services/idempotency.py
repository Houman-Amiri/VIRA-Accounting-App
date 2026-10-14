"""API mutation idempotency (Phase 4 §9).

An ``Idempotency-Key`` header value is claimed atomically in one write
transaction together with a hash of the request.  Outcomes:

* key unseen        → claim row (``response_status IS NULL``) and run the
  mutation; persist status + body on success.
* key seen, same request hash, response stored → replay the stored response.
* key seen, same request hash, still claimed (concurrent/in-flight) →
  ``409 idempotency_conflict``.
* key seen, different request hash → ``409 idempotency_key_reuse``.

Rows expire after :data:`IDEMPOTENCY_TTL_HOURS` (lazy cleanup).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ids import uuid7
from ..models import IdempotencyKey
from .errors import IdempotencyConflictError, IdempotencyKeyReuseError

IDEMPOTENCY_TTL_HOURS = 24


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def request_hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _expired(row: IdempotencyKey) -> bool:
    return row.expires_at < utc_now_iso()


class IdempotencyReplay(Exception):
    """Carries a stored response for replay."""

    def __init__(self, status: int, body: Any):
        self.status = status
        self.body = body


def claim_or_replay(
    session: Session,
    *,
    key: str,
    req_hash: str,
    execute: Callable[[], tuple[int, Any]],
) -> tuple[int, Any]:
    """Claim ``key`` for this request or return the stored/replayed result.

    ``execute`` runs inside the claim transaction and must return
    ``(response_status, response_body)``.  Concurrency-safe via the primary-key
    claim + ``BEGIN IMMEDIATE`` write sessions.
    """
    # Lazy cleanup of expired keys.
    now = utc_now_iso()
    session.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at < now))

    existing = session.get(IdempotencyKey, key)
    if existing is not None and not _expired(existing):
        if existing.request_hash != req_hash:
            raise IdempotencyKeyReuseError(
                "کلید idempotency قبلاً با درخواست دیگری استفاده شده است"
            )
        if existing.response_status is not None:
            raise IdempotencyReplay(
                existing.response_status,
                json.loads(existing.response_body) if existing.response_body else None,
            )
        raise IdempotencyConflictError("درخواست مشابه در حال پردازش است")

    claim = IdempotencyKey(
        key=key,
        request_hash=req_hash,
        response_status=None,
        response_body=None,
        created_at=now,
        expires_at=(
            datetime.now(UTC) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
        ).isoformat(timespec="seconds"),
    )
    try:
        with session.begin_nested():
            session.add(claim)
            session.flush()
    except IntegrityError as exc:
        raise IdempotencyConflictError("درخواست مشابه در حال پردازش است") from exc

    status, body = execute()
    claim.response_status = status
    claim.response_body = json.dumps(body, ensure_ascii=False, default=str)
    session.flush()
    return status, body


def purge_expired(session: Session) -> int:
    deleted = session.execute(
        delete(IdempotencyKey)
        .where(IdempotencyKey.expires_at < utc_now_iso())
        .returning(IdempotencyKey.key)
    ).scalars()
    return len(list(deleted))


__all__ = [
    "IDEMPOTENCY_TTL_HOURS",
    "IdempotencyReplay",
    "claim_or_replay",
    "purge_expired",
    "request_hash",
    "uuid7",
]

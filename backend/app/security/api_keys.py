"""Scoped ingest API keys (Phase 5 §2).

High-entropy secrets (`vira_sk_<prefix>_<secret>`) for the `ingest_api` role —
restricted strictly to posting draft journal entries and uploading receipts.
Only the SHA-256 hash is stored (keys have 256 bits of entropy, so a fast hash
is safe and enables O(1) prefix lookup + constant-time compare).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import ApiKey

KEY_PREFIX_LEN = 8
SECRET_BYTES = 32


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(full_key, key_prefix, key_hash)`` — the full key is shown ONCE."""
    prefix = secrets.token_hex(KEY_PREFIX_LEN)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    full_key = f"vira_sk_{prefix}_{secret}"
    return full_key, prefix, hash_secret(secret)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def split_key(full_key: str) -> tuple[str, str] | None:
    if not full_key.startswith("vira_sk_"):
        return None
    body = full_key[len("vira_sk_") :]
    if "_" not in body:
        return None
    prefix, secret = body.split("_", 1)
    return prefix, secret


def create_api_key(
    session: Session, *, name: str, created_by: str | None
) -> tuple[str, ApiKey]:
    full_key, prefix, key_hash = generate_api_key()
    row = ApiKey(
        id=uuid7(),
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        role="INGEST_API",
        created_by=created_by,
        created_at=utc_now_iso(),
    )
    session.add(row)
    session.flush()
    return full_key, row


def revoke_api_key(session: Session, key_id: str) -> ApiKey:
    row = session.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="api key not found")
    row.revoked_at = utc_now_iso()
    session.flush()
    return row


def authenticate_api_key(session: Session, presented: str) -> ApiKey | None:
    parts = split_key(presented)
    if parts is None:
        return None
    prefix, secret = parts
    row = session.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))
    if row is None or row.revoked_at is not None:
        return None
    if not hmac.compare_digest(row.key_hash, hash_secret(secret)):
        return None
    row.last_used_at = utc_now_iso()
    session.flush()
    return row


def require_ingest_key():
    """Dependency: authenticate an `ingest_api` key from the X-API-Key header.

    Replaces the cookie session — used ONLY on draft-entry creation and
    receipt upload routes.
    """

    def _guard(
        request: Request,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> ApiKey:
        if not x_api_key:
            raise HTTPException(status_code=401, detail="api key required")
        database = request.app.state.database
        with database.session() as session:
            row = authenticate_api_key(session, x_api_key)
            if row is None:
                raise HTTPException(status_code=401, detail="invalid api key")
            return row

    return _guard

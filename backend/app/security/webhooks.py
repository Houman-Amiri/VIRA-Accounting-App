"""Webhook signature verification + replay protection (Phase 5 §6).

All incoming bank-sync webhooks must carry:

* ``X-VIRA-Signature``: ``sha256=<hex HMAC-SHA256(raw_body, secret)>``
* ``X-VIRA-Timestamp``: unix seconds, must be within ±5 minutes
* ``X-VIRA-Event-Id``: unique per provider (deduplicated in ``webhook_events``)

Comparison is constant-time (:func:`hmac.compare_digest`).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

MAX_SKEW_SECONDS = 300


class WebhookError(ValueError):
    code = "webhook_rejected"


@dataclass(frozen=True)
class WebhookVerdict:
    ok: bool
    reason: str
    payload_digest: str


def compute_signature(secret: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify_webhook(
    *,
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp_raw: str | None,
    now: float | None = None,
) -> WebhookVerdict:
    digest = hashlib.sha256(body).hexdigest()
    if not signature or not timestamp_raw:
        return WebhookVerdict(ok=False, reason="missing signature or timestamp", payload_digest=digest)
    try:
        ts = int(timestamp_raw)
    except ValueError:
        return WebhookVerdict(ok=False, reason="invalid timestamp", payload_digest=digest)
    current = now if now is not None else time.time()
    if abs(current - ts) > MAX_SKEW_SECONDS:
        return WebhookVerdict(ok=False, reason="timestamp outside 5-minute window", payload_digest=digest)
    expected = compute_signature(secret, body)
    if not hmac.compare_digest(expected, signature):
        return WebhookVerdict(ok=False, reason="signature mismatch", payload_digest=digest)
    return WebhookVerdict(ok=True, reason="ok", payload_digest=digest)

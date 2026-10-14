"""Bank-sync webhook endpoint (Phase 5 §6) — HMAC + freshness + dedup."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..ids import uuid7
from ..models import WebhookEvent
from ..security.webhooks import verify_webhook
from ..services.security_audit import record_security_event
from .deps import get_db, get_settings

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class WebhookAck(BaseModel):
    status: str
    event_id: str | None = None


@router.post("/bank", response_model=WebhookAck)
async def bank_webhook(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_vira_signature: Annotated[str | None, Header(alias="X-VIRA-Signature")] = None,
    x_vira_timestamp: Annotated[str | None, Header(alias="X-VIRA-Timestamp")] = None,
    x_vira_event_id: Annotated[str | None, Header(alias="X-VIRA-Event-Id")] = None,
) -> WebhookAck:
    body = await request.body()
    # The webhook secret is envelope-encrypted in external_credentials.
    from ..models import ExternalCredential
    from ..security.envelope import get_envelope

    cred = session.scalar(
        select(ExternalCredential).where(
            ExternalCredential.provider == "bank_webhook",
            ExternalCredential.label == "signing_secret",
        )
    )
    secret = get_envelope().decrypt(cred.ciphertext) if cred is not None else ""
    if not secret:
        record_security_event(session, "WEBHOOK_REJECTED", detail={"reason": "no secret configured"})
        return WebhookAck(status="rejected")

    verdict = verify_webhook(
        secret=secret,
        body=body,
        signature=x_vira_signature,
        timestamp_raw=x_vira_timestamp,
    )
    if not verdict.ok:
        record_security_event(
            session, "WEBHOOK_REJECTED", detail={"reason": verdict.reason}
        )
        return WebhookAck(status="rejected")

    if x_vira_event_id:
        dup = session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.provider == "bank_webhook",
                WebhookEvent.event_id == x_vira_event_id,
            )
        )
        if dup is not None:
            return WebhookAck(status="duplicate", event_id=x_vira_event_id)
        try:
            session.add(
                WebhookEvent(
                    id=uuid7(),
                    provider="bank_webhook",
                    event_id=x_vira_event_id,
                    signature_ok=1,
                    received_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    payload_digest=verdict.payload_digest,
                )
            )
            session.flush()
        except IntegrityError:
            session.rollback()
            return WebhookAck(status="duplicate", event_id=x_vira_event_id)

    record_security_event(session, "WEBHOOK_ACCEPTED", detail={"event_id": x_vira_event_id})
    return WebhookAck(status="accepted", event_id=x_vira_event_id)

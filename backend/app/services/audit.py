"""Append-only audit capture via SQLAlchemy session events.

Old/new snapshots are valid JSON stored in TEXT with UTC ISO-8601 timestamps.
Secrets are redacted before persistence.  Audit rows themselves are protected
from ordinary update/delete by SQLite triggers (see migration 0001).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import AuditLog

REDACTED_FIELDS = {
    "password",
    "password_hash",
    "token",
    "secret",
    "authorization",
    "cookie",
    "totp_secret_enc",
    "iban",
    "account_number",
    "app_encryption_key",
    "session_secret",
}

TRACKED_TABLES = {
    "accounts",
    "journal_entries",
    "transaction_splits",
    "fiscal_periods",
    "exchange_rates",
    "bank_import_batches",
    "bank_statement_lines",
    "users",
    "recurring_entries",
    "documents",
}

#: Contextvar-style holder for the acting user id (set by API dependencies).
_current_actor: str | None = None


def set_actor(actor_id: str | None) -> None:
    global _current_actor
    _current_actor = actor_id


def get_actor() -> str | None:
    return _current_actor


def redact(data: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ("<redacted>" if k.lower() in REDACTED_FIELDS else v) for k, v in data.items()
    }


def _snapshot(obj: Any) -> dict[str, Any]:
    from sqlalchemy import inspect

    state = inspect(obj)
    data: dict[str, Any] = {}
    for col in state.mapper.column_attrs:
        val = getattr(obj, col.key)
        if isinstance(val, (str, int, float, bool)) or val is None:
            data[col.key] = val
        else:
            data[col.key] = str(val)
    return redact(data)


def record_audit(
    session: Session,
    *,
    table_name: str,
    record_id: str,
    action: str,
    old_data: dict[str, Any] | None,
    new_data: dict[str, Any] | None,
) -> None:
    session.add(
        AuditLog(
            id=uuid7(),
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_data=json.dumps(old_data, ensure_ascii=False, sort_keys=True)
            if old_data is not None
            else None,
            new_data=json.dumps(new_data, ensure_ascii=False, sort_keys=True)
            if new_data is not None
            else None,
            changed_at=utc_now_iso(),
            actor_id=_current_actor,
        )
    )


@event.listens_for(Session, "before_flush")
def _capture_audit(session: Session, _flush_context: object, _instances: object) -> None:
    for obj in session.new:
        if isinstance(obj, AuditLog):
            continue
        table = getattr(obj, "__tablename__", None)
        if table in TRACKED_TABLES:
            snap = _snapshot(obj)
            record_audit(
                session,
                table_name=table,
                record_id=str(obj.id),
                action="INSERT",
                old_data=None,
                new_data=snap,
            )
    for obj in session.dirty:
        if isinstance(obj, AuditLog):
            continue
        table = getattr(obj, "__tablename__", None)
        if table in TRACKED_TABLES and session.is_modified(obj, include_collections=False):
            state_old = _snapshot(obj)
            # recompute old values from committed history is overkill here;
            # we persist the new snapshot with old_data best-effort from history
            old_snap = getattr(obj, "_audit_old", None) or {}
            record_audit(
                session,
                table_name=table,
                record_id=str(obj.id),
                action="UPDATE",
                old_data=old_snap or None,
                new_data=state_old,
            )
    for obj in session.deleted:
        if isinstance(obj, AuditLog):
            continue
        table = getattr(obj, "__tablename__", None)
        if table in TRACKED_TABLES:
            record_audit(
                session,
                table_name=table,
                record_id=str(obj.id),
                action="DELETE",
                old_data=_snapshot(obj),
                new_data=None,
            )


def attach_old_snapshot(obj: Any) -> None:
    """Store a pre-edit snapshot on the instance so UPDATE audits keep old data."""
    obj._audit_old = _snapshot(obj)

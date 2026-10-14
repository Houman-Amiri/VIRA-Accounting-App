"""Journal entry API: create/update drafts, post, void, reverse."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..models import JournalEntry
from ..schemas.ledger import JournalEntryCreate, JournalEntryRead, SplitRead
from ..services.ledger import LedgerService
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(
    prefix="/api/v1/journal-entries",
    tags=["journal"],
    dependencies=[Depends(enforce_csrf)],
)


def _read(entry: JournalEntry) -> JournalEntryRead:
    return JournalEntryRead(
        id=entry.id,
        entry_number=entry.entry_number,
        transaction_date=entry.transaction_date,
        posted_at=entry.posted_at,
        payee=entry.payee,
        description=entry.description,
        status=entry.status,  # type: ignore[arg-type]
        reversed_entry_id=entry.reversed_entry_id,
        metadata=json.loads(entry.metadata_json or "{}"),
        version_id=entry.version_id,
        splits=[SplitRead.from_row(s) for s in entry.splits],
    )


@router.get("", response_model=list[JournalEntryRead])
def list_entries(
    session: Annotated[Session, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JournalEntryRead]:
    service = LedgerService(session)
    return [_read(e) for e in service.list_entries(status=status, limit=limit, offset=offset)]


@router.get("/{entry_id}", response_model=JournalEntryRead)
def get_entry(
    entry_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> JournalEntryRead:
    return _read(LedgerService(session).get_entry(entry_id))


@router.post("", response_model=JournalEntryRead, status_code=201)
def create_entry(
    payload: JournalEntryCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> JournalEntryRead:
    entry = LedgerService(session).create_draft(payload)
    return _read(entry)


@router.post("/{entry_id}/post", response_model=JournalEntryRead)
def post_entry(
    entry_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> JournalEntryRead:
    return _read(LedgerService(session).post(entry_id))


@router.post("/{entry_id}/void", response_model=JournalEntryRead)
def void_entry(
    entry_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER",))],
    reason: Annotated[str, Query(max_length=200)] = "",
) -> JournalEntryRead:
    return _read(LedgerService(session).void(entry_id, reason=reason))


@router.post("/{entry_id}/reverse", response_model=JournalEntryRead)
def reverse_entry(
    entry_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
    transaction_date: Annotated[str | None, Query()] = None,
) -> JournalEntryRead:
    return _read(LedgerService(session).reverse(entry_id, transaction_date=transaction_date))

"""Chart-of-accounts API (CRUD with optimistic locking)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..schemas.ledger import (
    NORMAL_BY_TYPE,
    AccountCreate,
    AccountLedgerRead,
    AccountRead,
    AccountUpdate,
)
from ..services.ledger import LedgerService
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(
    prefix="/api/v1/accounts",
    tags=["accounts"],
    dependencies=[Depends(enforce_csrf)],
)


@router.get("", response_model=list[AccountRead])
def list_accounts(
    session: Annotated[Session, Depends(get_db)],
    active_only: Annotated[bool, Query()] = False,
) -> list[AccountRead]:
    service = LedgerService(session)
    return [
        AccountRead(
            id=a.id,
            code=a.code,
            name=a.name,
            account_type=a.account_type,  # type: ignore[arg-type]
            normal_balance=a.normal_balance,  # type: ignore[arg-type]
            currency=a.currency,
            parent_id=a.parent_id,
            path=a.path,
            is_placeholder=bool(a.is_placeholder),
            is_active=bool(a.is_active),
            version_id=a.version_id,
        )
        for a in service.list_accounts(active_only=active_only)
    ]


@router.get("/{account_id}/ledger", response_model=AccountLedgerRead)
def account_ledger(
    account_id: str,
    session: Annotated[Session, Depends(get_db)],
    start: Annotated[str | None, Query(description="ISO date YYYY-MM-DD")] = None,
    end: Annotated[str | None, Query(description="ISO date YYYY-MM-DD")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AccountLedgerRead:
    """Drill-down for one statement line: the posted movements behind its balance."""
    return LedgerService(session).account_ledger(account_id, start=start, end=end, limit=limit)


@router.post("", response_model=AccountRead, status_code=201)
def create_account(
    payload: AccountCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> AccountRead:
    service = LedgerService(session)
    account = service.create_account(payload)
    return AccountRead(
        id=account.id,
        code=account.code,
        name=account.name,
        account_type=account.account_type,  # type: ignore[arg-type]
        normal_balance=NORMAL_BY_TYPE[account.account_type],
        currency=account.currency,
        parent_id=account.parent_id,
        path=account.path,
        is_placeholder=bool(account.is_placeholder),
        is_active=bool(account.is_active),
        version_id=account.version_id,
    )


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: str,
    payload: AccountUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> AccountRead:
    service = LedgerService(session)
    account = service.update_account(account_id, payload)
    return AccountRead(
        id=account.id,
        code=account.code,
        name=account.name,
        account_type=account.account_type,  # type: ignore[arg-type]
        normal_balance=account.normal_balance,  # type: ignore[arg-type]
        currency=account.currency,
        parent_id=account.parent_id,
        path=account.path,
        is_placeholder=bool(account.is_placeholder),
        is_active=bool(account.is_active),
        version_id=account.version_id,
    )

"""Journal entry API: create/update drafts, post, void, reverse.

Phase 4: keyset/cursor pagination (``cursor`` + ``X-Next-Cursor``) and optional
``Idempotency-Key`` on creation so retries cannot duplicate entries.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from ..models import JournalEntry
from ..schemas.ledger import (
    InvoiceCreate,
    InvoiceEntryUpdate,
    InvoiceRead,
    JournalEntryCreate,
    JournalEntryRead,
    JournalEntryUpdate,
    SplitRead,
)
from ..services.errors import DomainError
from ..services.idempotency import (
    IdempotencyReplay,
    claim_or_replay,
    request_hash,
)
from ..services.invoice import create_invoice, update_invoice_entry
from ..services.ledger import LedgerService
from ..services.persian import fa_count, fa_money_from_rial, jalali
from .deps import enforce_csrf, get_db, require_roles, require_user_or_ingest

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


def _encode_cursor(cursor: tuple[str, str]) -> str:
    raw = json.dumps(cursor, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(value: str) -> tuple[str, str]:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    date, ident = json.loads(raw)
    return str(date), str(ident)


@router.get("", response_model=list[JournalEntryRead])
def list_entries(
    session: Annotated[Session, Depends(get_db)],
    response: Response,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    cursor: Annotated[str | None, Query()] = None,
) -> list[JournalEntryRead]:
    service = LedgerService(session)
    if cursor is not None:
        page, next_cursor = service.list_entries_page(
            status=status, limit=limit, cursor=_decode_cursor(cursor)
        )
    else:
        # First page (or legacy OFFSET callers) — also expose the keyset cursor.
        page, next_cursor = service.list_entries_page(
            status=status, limit=limit, cursor=None
        )
        if offset:
            page = service.list_entries(status=status, limit=limit, offset=offset)
            next_cursor = (
                (page[-1].transaction_date, page[-1].id) if page else None
            )
    if next_cursor is not None:
        response.headers["X-Next-Cursor"] = _encode_cursor(next_cursor)
    return [_read(e) for e in page]


@router.get("/{entry_id}", response_model=JournalEntryRead)
def get_entry(
    entry_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> JournalEntryRead:
    return _read(LedgerService(session).get_entry(entry_id))


@router.post("/invoice", response_model=InvoiceRead, status_code=201)
def create_invoice_entry(
    payload: InvoiceCreate,
    session: Annotated[Session, Depends(get_db)],
    response: Response,
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvoiceRead:
    """Register a sale/purchase invoice as one balanced posted entry.

    The client sends what a paper invoice carries; the debit/credit mapping is
    derived here from the chart of accounts (1040/4010 for sales,
    1030/2010 for purchases) and the line detail is stored in the entry
    metadata.

    ``Idempotency-Key`` makes retries safe: a repeated click or a retried
    request returns the invoice already registered instead of posting a second
    entry for the same paper invoice.
    """
    if idempotency_key is not None:
        def _execute_invoice() -> tuple[int, dict[str, Any]]:
            return 201, create_invoice(session, payload).model_dump(mode="json")

        try:
            status, body = claim_or_replay(
                session,
                key=idempotency_key,
                req_hash=request_hash(payload.model_dump(mode="json")),
                execute=_execute_invoice,
            )
        except IdempotencyReplay as replay:
            response.status_code = replay.status
            return InvoiceRead(**replay.body)  # type: ignore[arg-type]
        response.status_code = status
        return InvoiceRead(**body)  # type: ignore[arg-type]
    return create_invoice(session, payload)


@router.post("", response_model=JournalEntryRead, status_code=201)
def create_entry(
    payload: JournalEntryCreate,
    session: Annotated[Session, Depends(get_db)],
    response: Response,
    _user: Annotated[tuple[str, object], Depends(require_user_or_ingest())],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JournalEntryRead:
    service = LedgerService(session)

    def _execute() -> tuple[int, dict[str, Any]]:
        entry = service.create_draft(payload)
        return 201, _read(entry).model_dump()

    if idempotency_key is not None:
        try:
            status, body = claim_or_replay(
                session,
                key=idempotency_key,
                req_hash=request_hash(payload.model_dump(mode="json")),
                execute=_execute,
            )
        except IdempotencyReplay as replay:
            response.status_code = replay.status
            return JournalEntryRead(**replay.body)  # type: ignore[arg-type]
        response.status_code = status
        return JournalEntryRead(**body)  # type: ignore[arg-type]

    entry = service.create_draft(payload)
    return _read(entry)


@router.get("/{entry_id}/invoice.pdf")
def invoice_document(
    entry_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER", "AUDITOR"))],
) -> Response:
    """فاکتور فروش — the printed document of one registered invoice entry.

    Same branded header as the proforma (logo + V.I.R.A), rendered from the
    invoice detail the entry already carries. WeasyPrint's native libraries are
    optional, so the very same HTML is returned when PDF is unavailable and the
    browser's «چاپ → ذخیره به‌عنوان PDF» still works.
    """
    from ..services.pdf import PRINTABLE_HTML_CSP, render_html

    entry = LedgerService(session).get_entry(entry_id)
    meta = json.loads(entry.metadata_json or "{}").get("invoice")
    if not isinstance(meta, dict):
        raise DomainError(
            f"سند شماره {entry.entry_number} از فاکتور ساخته نشده است؛ فاکتور چاپی ندارد"
        )
    context = {
        "company": {"name": "V.I.R.A", "tagline": "چاپ سه‌بعدی و فروش محصولات"},
        "invoice": {
            "entry_number": entry.entry_number,
            "entry_date": entry.transaction_date,
            "entry_date_jalali": jalali(entry.transaction_date),
            "kind": meta.get("kind", "sale"),
            "seller": meta.get("seller"),
            "buyer": meta.get("buyer"),
            "note": meta.get("note"),
            "status": entry.status,
            "status_note": {
                "DRAFT": "این فاکتور هنوز در دفاتر ثبت نشده است (پیش‌نویس).",
                "VOIDED": "این فاکتور ابطال شده است و در دفاتر نمی‌آید.",
            }.get(entry.status, ""),
            "lines": [
                {
                    "title": line.get("title", ""),
                    # quantities stay as typed; money is stored in Rials and
                    # printed in Tomans (÷10, exactly once, here at the edge).
                    "quantity": fa_count(Decimal(str(line.get("quantity", "0")))),
                    "unit_price": fa_money_from_rial(Decimal(str(line.get("unit_price", "0")))),
                    "line_total": fa_money_from_rial(Decimal(str(line.get("line_total", "0")))),
                }
                for line in meta.get("lines", [])
            ],
            "total": fa_money_from_rial(
                sum(
                    (Decimal(str(line.get("line_total", "0"))) for line in meta.get("lines", [])),
                    Decimal(0),
                )
            ),
        },
    }
    filename = f"invoice-{entry.entry_number}"
    try:
        return Response(
            content=request.app.state.pdf_renderer("invoice.html", context),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}.pdf"'},
        )
    except Exception:  # noqa: BLE001 - no WeasyPrint/native libs → printable HTML
        return Response(
            content=render_html("invoice.html", context),
            media_type="text/html",
            headers={
                "Content-Disposition": f'inline; filename="{filename}.html"',
                "Content-Security-Policy": PRINTABLE_HTML_CSP,
            },
        )


@router.put("/{entry_id}", response_model=JournalEntryRead)
def update_entry(
    entry_id: str,
    payload: JournalEntryUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> JournalEntryRead:
    """Correct an existing entry, keeping its status and versioning the change."""
    return _read(LedgerService(session).correct_entry(entry_id, payload))


@router.put("/{entry_id}/invoice", response_model=InvoiceRead)
def update_invoice(
    entry_id: str,
    payload: InvoiceEntryUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> InvoiceRead:
    """Edit an invoice-shaped entry; the server re-derives its balanced splits."""
    return update_invoice_entry(session, entry_id, payload)


@router.post("/{entry_id}/unpost", response_model=JournalEntryRead)
def unpost_entry(
    entry_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER",))],
) -> JournalEntryRead:
    """Return a posted entry to draft so it can be corrected («برگشت از ثبت»)."""
    return _read(LedgerService(session).unpost(entry_id))


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

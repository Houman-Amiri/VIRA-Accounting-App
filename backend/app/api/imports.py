"""Bank statement import API (idempotent uploads)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BankImportBatch, BankStatementLine
from ..services.bank_import import MAX_STATEMENT_BYTES, BankImportService
from ..services.categorize import Categorizer
from ..services.errors import FileRejectedError
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(
    prefix="/api/v1/imports",
    tags=["imports"],
    dependencies=[Depends(enforce_csrf)],
)


@router.post("/bank", status_code=201)
def import_bank_statement(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
    file: Annotated[UploadFile, File()],
    account_id: Annotated[str | None, Form()] = None,
    currency: Annotated[str, Form()] = "IRR",
) -> dict[str, object]:
    data = file.file.read(MAX_STATEMENT_BYTES + 1)
    if len(data) > MAX_STATEMENT_BYTES:
        raise FileRejectedError("statement exceeds 25 MB limit")
    service = BankImportService(session)
    service.reject_duplicate_file(account_id, data)
    batch = service.import_file(
        filename=file.filename or "statement",
        data=data,
        account_id=account_id,
        currency=currency,
    )
    categorizer = Categorizer(session)
    for line in batch.lines:
        categorizer.categorize_line(line)
    session.flush()
    return {
        "batch_id": batch.id,
        "file_format": batch.file_format,
        "file_sha256": batch.file_sha256,
        "lines_imported": batch.line_count,
    }


@router.get("/batches")
def list_batches(
    session: Annotated[Session, Depends(get_db)],
) -> list[dict[str, object]]:
    rows = session.scalars(
        select(BankImportBatch).order_by(BankImportBatch.imported_at.desc())
    )
    return [
        {
            "id": b.id,
            "source_filename": b.source_filename,
            "file_format": b.file_format,
            "imported_at": b.imported_at,
            "status": b.status,
            "line_count": b.line_count,
        }
        for b in rows
    ]


@router.get("/lines")
def list_lines(
    session: Annotated[Session, Depends(get_db)],
    batch_id: str | None = None,
    account_id: str | None = None,
) -> list[dict[str, object]]:
    stmt = select(BankStatementLine).order_by(BankStatementLine.value_date)
    if batch_id:
        stmt = stmt.where(BankStatementLine.batch_id == batch_id)
    if account_id:
        stmt = stmt.where(BankStatementLine.account_id == account_id)
    rows = session.scalars(stmt)
    return [
        {
            "id": ln.id,
            "account_id": ln.account_id,
            "value_date": ln.value_date,
            "payee_raw": ln.payee_raw,
            "description_raw": ln.description_raw,
            "amount_scaled": ln.amount,
            "currency": ln.currency,
            "category_suggestion": ln.category_suggestion,
            "status": ln.status,
        }
        for ln in rows
    ]

class LineStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(UNMATCHED|MATCHED|IGNORED)$")


@router.post("/lines/{line_id}/status")
def set_line_status(
    line_id: str,
    payload: LineStatusUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> dict[str, object]:
    """Mark a statement line ignored / matched / back to unmatched.

    The reconciliation screen needs this so «نادیده گرفتن» and «تطبیق» are real
    actions instead of local UI state: an ignored line leaves the work list, and
    a matched one is no longer offered as a candidate.
    """
    line = session.get(BankStatementLine, line_id)
    if line is None:
        from ..services.errors import NotFoundError

        raise NotFoundError("ردیف صورت‌حساب یافت نشد")
    line.status = payload.status
    session.flush()
    return {"id": line.id, "status": line.status}

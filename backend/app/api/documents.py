"""Receipt/document upload + authenticated delivery (content-addressed)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..ids import uuid7
from ..models import Document
from ..services.errors import NotFoundError
from ..services.ocr import parse_receipt_text
from ..services.storage import save_receipt
from .deps import enforce_csrf, get_db, get_settings, require_roles

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
    dependencies=[Depends(enforce_csrf)],
)


@router.post("/receipts", status_code=201)
def upload_receipt(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
    file: Annotated[UploadFile, File()],
    journal_entry_id: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    assert settings.receipt_dir is not None
    data = file.file.read()
    meta = save_receipt(data, file.filename or "receipt", settings.receipt_dir)
    existing = session.scalar(select(Document).where(Document.sha256 == meta["sha256"]))
    if existing is not None:
        return {"id": existing.id, "sha256": existing.sha256, "duplicate": True}
    doc = Document(
        id=uuid7(),
        sha256=str(meta["sha256"]),
        media_type=str(meta["media_type"]),
        original_name=str(meta["original_name"]),
        size_bytes=int(str(meta["size_bytes"])),
        storage_path=str(meta["storage_path"]),
        journal_entry_id=journal_entry_id,
        ocr_status="NONE",
        uploaded_at=str(meta["uploaded_at"]),
    )
    session.add(doc)
    session.flush()
    return {"id": doc.id, "sha256": doc.sha256, "duplicate": False}


@router.get("/receipts/{doc_id}")
def get_receipt(
    doc_id: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise NotFoundError(f"document {doc_id} not found")
    assert settings.receipt_dir is not None
    path = Path(settings.receipt_dir) / doc.storage_path
    if not path.exists():
        raise NotFoundError("stored file missing")
    return Response(
        content=path.read_bytes(),
        media_type=doc.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.id}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.post("/receipts/{doc_id}/ocr")
def run_ocr(
    doc_id: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> dict[str, object]:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise NotFoundError(f"document {doc_id} not found")
    assert settings.receipt_dir is not None
    path = Path(settings.receipt_dir) / doc.storage_path
    try:
        from ..services.ocr import default_engine

        text = default_engine().extract_text(path.read_bytes())
        parsed = parse_receipt_text(text) if text else None
        doc.ocr_status = "DONE" if parsed else "FAILED"
        if parsed is not None:

            doc.ocr_data_json = parsed.model_dump_json()
        session.flush()
        return {"status": doc.ocr_status, "data": parsed.model_dump() if parsed else None}
    except Exception:
        doc.ocr_status = "FAILED"
        session.flush()
        return {"status": "FAILED", "data": None}

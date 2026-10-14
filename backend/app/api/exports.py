"""Export endpoints (Phase 5 §2/§7).

* ``POST /exports/database-dump`` — unencrypted full SQLite dump: **sudo**
  required, logged as ``BACKUP_EXPORTED``.
* ``GET /exports/ledger.csv`` — formula-injection-safe CSV of posted splits
  (exact fixed-scale strings, no float formatting).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import Settings
from ..security.session import SessionUser
from ..security.sudo import require_sudo
from ..services.export import write_csv_safe
from ..services.security_audit import record_security_event
from .deps import enforce_csrf, get_db, get_settings

router = APIRouter(
    prefix="/api/v1/exports",
    tags=["exports"],
    dependencies=[Depends(enforce_csrf)],
)

CSV_COLUMNS = [
    "entry_number",
    "transaction_date",
    "account_code",
    "account_name",
    "memo",
    "debit",
    "credit",
    "currency",
]


@router.post("/database-dump")
def export_database_dump(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> Response:
    """Full unencrypted DB dump — high-risk: sudo re-auth + security log."""

    assert settings.sqlite_database_path is not None
    src_path = Path(settings.sqlite_database_path)
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(":memory:")
    try:
        src.backup(dst)
        dump_bytes = dst.serialize()
    finally:
        src.close()
        dst.close()
    record_security_event(
        session, "BACKUP_EXPORTED", actor_id=user.user_id, detail={"kind": "sqlite-dump"}
    )
    return Response(
        content=dump_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="vira-dump.sqlite3"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/ledger.csv")
def export_ledger_csv(session: Annotated[Session, Depends(get_db)]) -> Response:
    rows = session.execute(
        text(
            "SELECT je.entry_number AS entry_number, je.transaction_date AS transaction_date,"
            " a.code AS account_code, a.name AS account_name, s.memo AS memo,"
            " s.debit AS debit, s.credit AS credit, s.currency AS currency"
            " FROM transaction_splits s"
            " JOIN journal_entries je ON je.id = s.journal_entry_id"
            " JOIN accounts a ON a.id = s.account_id"
            " WHERE je.status = 'POSTED'"
            " ORDER BY je.transaction_date, je.entry_number"
        )
    ).mappings()
    from ..money import from_scaled

    out_rows = [
        {
            **dict(r),
            "debit": f"{from_scaled(int(r['debit'])):.4f}",
            "credit": f"{from_scaled(int(r['credit'])):.4f}",
        }
        for r in rows
    ]
    csv_text = write_csv_safe(out_rows, CSV_COLUMNS)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="vira-ledger.csv"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )

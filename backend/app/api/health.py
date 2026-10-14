"""Health endpoints: liveness + readiness (DB, pragmas, invariants, migrations)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import check_invariants, verify_pragmas
from .deps import get_db, get_settings

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    from typing import cast

    from sqlalchemy import Engine

    engine = cast(Engine, session.get_bind())
    pragmas = verify_pragmas(engine)
    invariants = check_invariants(engine)
    revision = session.execute(
        text("SELECT version_num FROM alembic_version LIMIT 1")
    ).scalar()
    receipt_ok = settings.receipt_dir is not None and settings.receipt_dir.exists()
    healthy = (
        invariants.get("integrity_check") == "ok"
        and invariants.get("foreign_key_violations") == 0
        and invariants.get("balanced") is True
        and receipt_ok
    )
    return {
        "status": "ready" if healthy else "degraded",
        "sqlite_version": sqlite3.sqlite_version,
        "pragmas": pragmas,
        "alembic_revision": revision,
        "invariants": invariants,
        "receipt_storage_writable": receipt_ok,
    }

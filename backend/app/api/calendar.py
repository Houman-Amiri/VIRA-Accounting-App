"""Event-sourced installation preference in the existing append-only SQLite trail.

No schema revision changes: old versions can still read the DB after file rollback.
Each change carries a monotonic revision, so wall-clock rollback does not revert
preferences. BEGIN IMMEDIATE in get_db serializes CAS across processes. The trail
is part of normal SQLite backups and never pruned/updated/deleted by this API.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SecurityAuditLog
from ..schemas.calendar import CalendarRead, CalendarUpdate
from ..security.session import SessionUser
from ..services.errors import DomainError, StaleVersionError
from ..services.security_audit import record_security_event
from .deps import enforce_csrf, get_db, require_roles

EVENT = "CALENDAR_PREFERENCE_UPDATED"
router = APIRouter(
    prefix="/api/v1/settings/calendar", tags=["settings"], dependencies=[Depends(enforce_csrf)]
)


class CalendarPreferenceCorrupt(DomainError):
    status = 503
    code = "calendar_preference_corrupt"
    title = "Calendar preference unavailable"


def _read(session: Session) -> CalendarRead:
    current = CalendarRead(calendar="jalali", version_id=0)
    revisions: set[int] = set()
    # Settings edits are rare. Validate the whole stream instead of silently
    # masking a corrupt latest event or depending on timestamps / physical rowids.
    for detail in session.scalars(
        select(SecurityAuditLog.detail).where(SecurityAuditLog.event == EVENT)
    ):
        try:
            entry = CalendarUpdate.model_validate_json(detail or "")
            if entry.version_id < 1 or entry.version_id in revisions:
                raise ValueError("invalid calendar revision")
            revisions.add(entry.version_id)
            if entry.version_id > current.version_id:
                current = CalendarRead(**entry.model_dump())
        except (ValidationError, ValueError) as exc:
            raise CalendarPreferenceCorrupt(
                "خواندن تنظیم تقویم ناموفق است؛ پیش از ثبت تاریخ، تنظیمات را بررسی کنید."
            ) from exc
    if len(revisions) != current.version_id:
        raise CalendarPreferenceCorrupt("تاریخچهٔ تنظیم تقویم ناقص است؛ ذخیره متوقف شد.")
    return current


@router.get("", response_model=CalendarRead)
def read_calendar(
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER", "AUDITOR"))],
) -> CalendarRead:
    return _read(session)


@router.put("", response_model=CalendarRead)
def update_calendar(
    body: CalendarUpdate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> CalendarRead:
    current = _read(session)
    if current.version_id != body.version_id:
        raise StaleVersionError("تنظیم تقویم تغییر کرده است؛ دوباره بارگذاری و انتخاب کنید.")
    if current.calendar == body.calendar:
        return current
    result = CalendarRead(calendar=body.calendar, version_id=current.version_id + 1)
    record_security_event(
        session,
        EVENT,
        actor_id=user.user_id,
        detail={"calendar": result.calendar, "version_id": result.version_id},
    )
    return result

"""Authenticated shared pricing settings, persisted in the application's SQLite."""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..ids import utc_now_iso
from ..models.pricing import PricingSettings
from ..schemas.pricing import PricingRead, PricingUpdate, PricingValues
from ..security.session import SessionUser
from ..services.errors import NotFoundError, StaleVersionError
from ..services.security_audit import record_security_event
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(prefix="/api/v1/settings/pricing", tags=["settings"], dependencies=[Depends(enforce_csrf)])


def _read(session: Session) -> PricingRead:
    row = session.get(PricingSettings, 1)
    if row is None:
        raise NotFoundError("تنظیمات قیمت‌گذاری پیدا نشد؛ وضعیت مهاجرت پایگاه‌داده را بررسی کنید.")
    return PricingRead(**{
        field: getattr(row, field) / (Decimal(1) if field == "profit_factor" else Decimal(10))
        for field in PricingValues.model_fields
    }, version_id=row.version_id, updated_at=row.updated_at)


@router.get("", response_model=PricingRead)
def read_pricing(
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER", "AUDITOR"))],
) -> PricingRead:
    return _read(session)


@router.put("", response_model=PricingRead)
def update_pricing(
    body: PricingUpdate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> PricingRead:
    values = {
        field: getattr(body, field) * (Decimal(1) if field == "profit_factor" else Decimal(10))
        for field in PricingValues.model_fields
    }
    changed = session.execute(update(PricingSettings).where(
        PricingSettings.id == 1, PricingSettings.version_id == body.version_id,
    ).values(**values, version_id=body.version_id + 1, updated_at=utc_now_iso()).returning(PricingSettings.id)).scalar_one_or_none()
    if changed is None:
        raise StaleVersionError("ثابت‌ها توسط کاربر دیگری تغییر کرده‌اند؛ دوباره بارگذاری کنید.")
    record_security_event(session, "PRICING_CONSTANTS_UPDATED", actor_id=user.user_id,
                          detail={"version_id": body.version_id + 1})
    session.expire_all()
    return _read(session)

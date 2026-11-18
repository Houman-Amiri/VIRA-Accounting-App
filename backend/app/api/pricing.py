"""Authenticated shared pricing settings, persisted in the application's SQLite."""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models.pricing import PricingCustomConstant, PricingSettings, PricingVariable
from ..schemas.pricing import (
    MAX_PERCENT,
    PricingCustomConstantCreate,
    PricingCustomConstantRead,
    PricingCustomConstantUpdate,
    PricingRead,
    PricingUpdate,
    PricingValues,
    PricingVariableCreate,
    PricingVariableRead,
    PricingVariableUpdate,
)
from ..security.session import SessionUser
from ..services.errors import DomainError, NotFoundError, StaleVersionError
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


# ------------------------------------------------- owner-defined constants ---
@router.get("/constants", response_model=list[PricingCustomConstantRead])
def list_custom_constants(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER", "AUDITOR"))],
) -> list[PricingCustomConstantRead]:
    """The owner's own pricing constants, in display order."""
    rows = session.scalars(
        select(PricingCustomConstant).order_by(
            PricingCustomConstant.position, PricingCustomConstant.created_at
        )
    )
    return [_read_custom(row) for row in rows]


@router.post("/constants", response_model=PricingCustomConstantRead, status_code=201)
def create_custom_constant(
    body: PricingCustomConstantCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> PricingCustomConstantRead:
    if _custom_name_taken(session, body.name):
        raise DomainError("ثابتی با این نام از قبل وجود دارد؛ نام دیگری انتخاب کنید.")
    now = utc_now_iso()
    last = session.scalar(select(func.max(PricingCustomConstant.position))) or 0
    row = PricingCustomConstant(
        id=uuid7(),
        name=body.name,
        method=body.method,
        value=_to_storage(body.value, body.method),
        is_active=1 if body.is_active else 0,
        position=int(last) + 1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    record_security_event(
        session,
        "PRICING_CONSTANT_CREATED",
        actor_id=user.user_id,
        detail={"constant_id": row.id, "method": row.method},
    )
    return _read_custom(row)


@router.patch("/constants/{constant_id}", response_model=PricingCustomConstantRead)
def update_custom_constant(
    constant_id: str,
    body: PricingCustomConstantUpdate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> PricingCustomConstantRead:
    """Change the name, the method or the value of a custom constant."""
    row = session.get(PricingCustomConstant, constant_id)
    if row is None:
        raise NotFoundError("ثابت قیمت‌گذاری پیدا نشد")
    payload = body.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] is not None:
        if _custom_name_taken(session, payload["name"], exclude_id=row.id):
            raise DomainError("ثابتی با این نام از قبل وجود دارد؛ نام دیگری انتخاب کنید.")
        row.name = payload["name"]
    if payload.get("method") is not None:
        row.method = payload["method"]
    if payload.get("value") is not None:
        row.value = _to_storage(payload["value"], payload.get("method") or row.method)
    if payload.get("is_active") is not None:
        row.is_active = 1 if payload["is_active"] else 0
    if row.method.startswith("PERCENT") and row.value > MAX_PERCENT:
        raise DomainError(f"درصد نمی‌تواند از {MAX_PERCENT} بیشتر باشد")
    row.updated_at = utc_now_iso()
    session.flush()
    record_security_event(
        session,
        "PRICING_CONSTANT_UPDATED",
        actor_id=user.user_id,
        detail={"constant_id": row.id, "method": row.method},
    )
    return _read_custom(row)


@router.delete("/constants/{constant_id}", status_code=204)
def delete_custom_constant(
    constant_id: str,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> Response:
    row = session.get(PricingCustomConstant, constant_id)
    if row is None:
        raise NotFoundError("ثابت قیمت‌گذاری پیدا نشد")
    session.delete(row)
    session.flush()
    record_security_event(
        session,
        "PRICING_CONSTANT_DELETED",
        actor_id=user.user_id,
        detail={"constant_id": constant_id},
    )
    return Response(status_code=204)


def _to_storage(value: Decimal, method: str) -> Decimal:
    """Money is stored in Rials (×10 from the Toman the API speaks); a percent is not."""
    if method.startswith("PERCENT"):
        return value
    return value * Decimal(10)


def _from_storage(row: PricingCustomConstant) -> Decimal:
    if row.method.startswith("PERCENT"):
        return row.value
    return row.value / Decimal(10)


def _read_custom(row: PricingCustomConstant) -> PricingCustomConstantRead:
    return PricingCustomConstantRead(
        id=row.id,
        name=row.name,
        method=row.method,  # type: ignore[arg-type]
        value=f"{_from_storage(row):.4f}",
        is_active=bool(row.is_active),
        position=row.position,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _custom_name_taken(
    session: Session, name: str, *, exclude_id: str | None = None
) -> bool:
    stmt = select(PricingCustomConstant.id).where(
        func.lower(PricingCustomConstant.name) == name.strip().lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(PricingCustomConstant.id != exclude_id)
    return session.scalar(stmt) is not None


# -------------------------------------------------- owner-defined variables ---
def _variable_storage(basis: str, value: Decimal) -> Decimal:
    """Money is stored as scaled Rial (×10); a percentage is stored as-is."""
    if basis.startswith("PERCENT"):
        return value
    return value * Decimal(10)


def _variable_value(row: PricingVariable) -> Decimal:
    if row.basis.startswith("PERCENT"):
        return row.value
    return row.value / Decimal(10)


def _read_variable(row: PricingVariable) -> PricingVariableRead:
    return PricingVariableRead(
        id=row.id,
        name=row.name,
        scope=row.scope,  # type: ignore[arg-type]
        basis=row.basis,  # type: ignore[arg-type]
        allocation=row.allocation,  # type: ignore[arg-type]
        value=f"{_variable_value(row):.4f}",
        is_active=bool(row.is_active),
        position=row.position,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _variable_name_taken(
    session: Session, name: str, *, exclude_id: str | None = None
) -> bool:
    stmt = select(PricingVariable.id).where(
        func.lower(PricingVariable.name) == name.strip().lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(PricingVariable.id != exclude_id)
    return session.scalar(stmt) is not None


def _normalized_allocation(scope: str, allocation: str) -> str:
    """A per-piece variable is inherently spread over the pieces."""
    return "SPLIT" if scope == "PER_UNIT" else allocation


@router.get("/variables", response_model=list[PricingVariableRead])
def list_variables(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER", "AUDITOR"))],
) -> list[PricingVariableRead]:
    """The owner's variables (default values), in display order."""
    rows = session.scalars(
        select(PricingVariable).order_by(PricingVariable.position, PricingVariable.created_at)
    )
    return [_read_variable(row) for row in rows]


@router.post("/variables", response_model=PricingVariableRead, status_code=201)
def create_variable(
    body: PricingVariableCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> PricingVariableRead:
    if _variable_name_taken(session, body.name):
        raise DomainError("متغیری با این نام از قبل وجود دارد؛ نام دیگری انتخاب کنید.")
    now = utc_now_iso()
    last = session.scalar(select(func.max(PricingVariable.position))) or 0
    row = PricingVariable(
        id=uuid7(),
        name=body.name,
        scope=body.scope,
        basis=body.basis,
        allocation=_normalized_allocation(body.scope, body.allocation),
        value=_variable_storage(body.basis, body.value),
        is_active=1 if body.is_active else 0,
        position=int(last) + 1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    record_security_event(
        session,
        "PRICING_VARIABLE_CREATED",
        actor_id=user.user_id,
        detail={"variable_id": row.id, "scope": row.scope, "basis": row.basis},
    )
    return _read_variable(row)


@router.patch("/variables/{variable_id}", response_model=PricingVariableRead)
def update_variable(
    variable_id: str,
    body: PricingVariableUpdate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> PricingVariableRead:
    """Change a variable's name, scope, basis, allocation, value or on/off."""
    row = session.get(PricingVariable, variable_id)
    if row is None:
        raise NotFoundError("متغیر قیمت‌گذاری پیدا نشد")
    payload = body.model_dump(exclude_unset=True)
    previous_basis = row.basis
    # What the owner sees today, so changing only the basis does not silently
    # divide his number by ten (12.5% must stay 12.5, not become 1.25 Toman).
    display_value = _variable_value(row)
    if "name" in payload and payload["name"] is not None:
        if _variable_name_taken(session, payload["name"], exclude_id=row.id):
            raise DomainError("متغیری با این نام از قبل وجود دارد؛ نام دیگری انتخاب کنید.")
        row.name = payload["name"]
    if payload.get("scope") is not None:
        row.scope = payload["scope"]
    if payload.get("basis") is not None:
        row.basis = payload["basis"]
    if payload.get("allocation") is not None:
        row.allocation = payload["allocation"]
    if payload.get("value") is not None:
        row.value = _variable_storage(row.basis, payload["value"])
    elif row.basis != previous_basis:
        row.value = _variable_storage(row.basis, display_value)
    if payload.get("is_active") is not None:
        row.is_active = 1 if payload["is_active"] else 0
    row.allocation = _normalized_allocation(row.scope, row.allocation)
    if row.basis.startswith("PERCENT") and row.value > MAX_PERCENT:
        raise DomainError(f"درصد نمی‌تواند از {MAX_PERCENT} بیشتر باشد")
    row.updated_at = utc_now_iso()
    session.flush()
    record_security_event(
        session,
        "PRICING_VARIABLE_UPDATED",
        actor_id=user.user_id,
        detail={"variable_id": row.id, "scope": row.scope, "basis": row.basis},
    )
    return _read_variable(row)


@router.delete("/variables/{variable_id}", status_code=204)
def delete_variable(
    variable_id: str,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles("OWNER", "BOOKKEEPER"))],
) -> Response:
    row = session.get(PricingVariable, variable_id)
    if row is None:
        raise NotFoundError("متغیر قیمت‌گذاری پیدا نشد")
    session.delete(row)
    session.flush()
    record_security_event(
        session,
        "PRICING_VARIABLE_DELETED",
        actor_id=user.user_id,
        detail={"variable_id": variable_id},
    )
    return Response(status_code=204)

"""Operations API — انبار (warehouse), سفارش‌ها (orders), تولید (production).

Three routers, all Persian-facing in the UI; money/quantities travel as
fixed-scale strings. Mutations require OWNER/BOOKKEEPER; reads allow AUDITOR.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..ids import today_iso
from ..schemas.catalog import (
    CatalogCategory,
    CatalogCreate,
    CatalogDeletion,
    CatalogRead,
    CatalogState,
)
from ..schemas.operations import (
    InventoryAlarm,
    InventoryItemCreate,
    InventoryItemRead,
    InventoryItemUpdate,
    InventorySummary,
    OrderCreate,
    OrderItemRead,
    OrderRead,
    OrderSummary,
    OrderUpdate,
    ProductionJobCreate,
    ProductionJobRead,
    ProductionJobUpdate,
    ProductionSummary,
    SalesReport,
    StockMovementCreate,
    StockMovementRead,
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)
from ..security.session import SessionUser
from ..services.catalog import CatalogService
from ..services.operations import OperationsService
from .deps import enforce_csrf, get_db, require_roles

warehouse = APIRouter(
    prefix="/api/v1/warehouse", tags=["warehouse"], dependencies=[Depends(enforce_csrf)]
)
orders = APIRouter(prefix="/api/v1/orders", tags=["orders"], dependencies=[Depends(enforce_csrf)])
production = APIRouter(
    prefix="/api/v1/production", tags=["production"], dependencies=[Depends(enforce_csrf)]
)

READ_ROLES = ("OWNER", "BOOKKEEPER", "AUDITOR")
WRITE_ROLES = ("OWNER", "BOOKKEEPER")


def _money(value: Decimal | None) -> str:
    return f"{Decimal(value or 0):.4f}"


# ------------------------------------------------------------------ helpers ---
def _supplier_read(supplier: Any) -> SupplierRead:
    return SupplierRead(
        id=supplier.id,
        name=supplier.name,
        address=supplier.address,
        phone=supplier.phone,
        score_price=supplier.score_price,
        score_quality=supplier.score_quality,
        score_delivery=supplier.score_delivery,
        notes=supplier.notes,
        is_active=bool(supplier.is_active),
        version_id=supplier.version_id,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


def _item_read(item: Any) -> InventoryItemRead:
    quantity = Decimal(item.quantity)
    min_quantity = Decimal(item.min_quantity)
    unit_price = Decimal(item.unit_price)
    supplier = getattr(item, "supplier", None)
    return InventoryItemRead(
        id=item.id,
        name=item.name,
        kind=item.kind,
        kind_name=item.item_type.name,
        unit_name=item.item_unit.name,
        color=item.color,
        unit=item.unit,
        quantity=quantity,
        min_quantity=min_quantity,
        unit_price=unit_price,
        supplier_id=item.supplier_id,
        supplier_name=supplier.name if supplier is not None else None,
        purchased_at=item.purchased_at,
        notes=item.notes,
        is_active=bool(item.is_active),
        version_id=item.version_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
        low_stock=quantity <= min_quantity,
        value=quantity * unit_price,
    )


def _movement_read(movement: Any) -> StockMovementRead:
    return StockMovementRead(
        id=movement.id,
        item_id=movement.item_id,
        item_name=movement.item.name if movement.item is not None else "",
        kind=movement.kind,
        quantity=Decimal(movement.quantity),
        unit_cost=Decimal(movement.unit_cost) if movement.unit_cost is not None else None,
        reason=movement.reason,
        reference_id=movement.reference_id,
        note=movement.note,
        occurred_at=movement.occurred_at,
        created_at=movement.created_at,
    )


def _order_item_read(line: Any) -> OrderItemRead:
    return OrderItemRead(
        id=line.id,
        position=line.position,
        product_name=line.product_name,
        variant=line.variant,
        quantity=Decimal(line.quantity),
        unit_price=Decimal(line.unit_price),
        unit_cost=Decimal(line.unit_cost),
        weight_g=Decimal(line.weight_g),
        print_hours=Decimal(line.print_hours),
        inventory_item_id=line.inventory_item_id,
        notes=line.notes,
    )


def _order_read(order: Any) -> OrderRead:
    items = [_order_item_read(line) for line in order.items]
    total = sum((i.quantity * i.unit_price for i in items), Decimal(0))
    cost = sum((i.quantity * i.unit_cost for i in items), Decimal(0))
    return OrderRead(
        id=order.id,
        order_number=order.order_number,
        order_date=order.order_date,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        customer_address=order.customer_address,
        status=order.status,
        channel=order.channel,
        notes=order.notes,
        version_id=order.version_id,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=items,
        total=total,
        total_cost=cost,
        profit=total - cost,
    )


def _job_read(session: Session, job: Any) -> ProductionJobRead:
    order_number = None
    if job.order_id:
        from ..models import Order

        order = session.get(Order, job.order_id)
        order_number = order.order_number if order is not None else None
    filament_name = None
    if job.filament_item_id:
        from ..models import InventoryItem

        item = session.get(InventoryItem, job.filament_item_id)
        filament_name = item.name if item is not None else None
    product_name = None
    if job.product_item_id:
        from ..models import InventoryItem

        item = session.get(InventoryItem, job.product_item_id)
        product_name = item.name if item is not None else None
    return ProductionJobRead(
        id=job.id,
        job_number=job.job_number,
        order_id=job.order_id,
        order_number=order_number,
        order_item_id=job.order_item_id,
        product_name=job.product_name,
        variant=job.variant,
        channel=job.channel,
        quantity=Decimal(job.quantity),
        status=job.status,
        filament_item_id=job.filament_item_id,
        filament_item_name=filament_name,
        product_item_id=job.product_item_id,
        product_item_name=product_name,
        filament_grams=Decimal(job.filament_grams),
        print_hours=Decimal(job.print_hours),
        unit_cost=Decimal(job.unit_cost),
        unit_price=Decimal(job.unit_price),
        note=job.note,
        started_at=job.started_at,
        finished_at=job.finished_at,
        version_id=job.version_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# ----------------------------------------------------------------- suppliers ---
@warehouse.get("/suppliers", response_model=list[SupplierRead])
def list_suppliers(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    active_only: Annotated[bool, Query()] = False,
) -> list[SupplierRead]:
    return [_supplier_read(s) for s in OperationsService(session).list_suppliers(active_only=active_only)]


@warehouse.get("/suppliers/suggestions", response_model=list[SupplierRead])
def supplier_suggestions(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    item_id: Annotated[str | None, Query()] = None,
) -> list[SupplierRead]:
    """Best supplier to buy from — ranked by price/quality/delivery scores."""
    service = OperationsService(session)
    return [_supplier_read(s) for s in service.supplier_suggestions(item_id=item_id)]


@warehouse.post("/suppliers", response_model=SupplierRead, status_code=201)
def create_supplier(
    payload: SupplierCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[SessionUser, Depends(require_roles(*WRITE_ROLES))],
) -> SupplierRead:
    row = OperationsService(session).create_supplier(payload)
    CatalogService(session).event("suppliers", row, "created", _user.user_id)
    return _supplier_read(row)


@warehouse.patch("/suppliers/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[SessionUser, Depends(require_roles(*WRITE_ROLES))],
) -> SupplierRead:
    row = OperationsService(session).update_supplier(supplier_id, payload)
    CatalogService(session).event("suppliers", row, "updated", _user.user_id)
    return _supplier_read(row)



@warehouse.delete("/suppliers/{supplier_id}", response_model=CatalogDeletion)
def delete_supplier(
    supplier_id: str,
    version_id: Annotated[int, Query(ge=1)],
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles(*WRITE_ROLES))],
) -> CatalogDeletion:
    return CatalogService(session).delete("suppliers", supplier_id, version_id, user.user_id)


def _catalog_read(row: Any) -> CatalogRead:
    return CatalogRead(id=row.id, name=row.name, is_active=bool(row.is_active), version_id=row.version_id,
        required_unit=getattr(row,"required_unit",None), production_role=getattr(row,"production_role","NONE"))


@warehouse.get("/catalog/{category}", response_model=list[CatalogRead])
def list_catalog(
    category: CatalogCategory,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles(*READ_ROLES))],
    active_only: Annotated[bool, Query()] = False,
) -> list[CatalogRead]:
    return [_catalog_read(row) for row in CatalogService(session).list(category, active_only=active_only)]


@warehouse.post("/catalog/{category}", response_model=CatalogRead, status_code=201)
def create_catalog(
    category: CatalogCategory,
    payload: CatalogCreate,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles(*WRITE_ROLES))],
) -> CatalogRead:
    return _catalog_read(CatalogService(session).create(category, payload.name, user.user_id))


@warehouse.patch("/catalog/{category}/{ident}", response_model=CatalogRead)
def activate_catalog(
    category: CatalogCategory, ident: str, payload: CatalogState,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles(*WRITE_ROLES))],
) -> CatalogRead:
    return _catalog_read(CatalogService(session).activate(category, ident, payload.version_id, payload.is_active, user.user_id))


@warehouse.delete("/catalog/{category}/{ident}", response_model=CatalogDeletion)
def delete_catalog(
    category: CatalogCategory, ident: str, version_id: Annotated[int, Query(ge=1)],
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[SessionUser, Depends(require_roles(*WRITE_ROLES))],
) -> CatalogDeletion:
    return CatalogService(session).delete(category, ident, version_id, user.user_id)


# ----------------------------------------------------------------- inventory ---
@warehouse.get("/items", response_model=list[InventoryItemRead])
def list_items(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    kind: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    low_only: Annotated[bool, Query()] = False,
) -> list[InventoryItemRead]:
    service = OperationsService(session)
    return [
        _item_read(i)
        for i in service.list_items(kind=kind, search=search, low_only=low_only)
    ]


@warehouse.post("/items", response_model=InventoryItemRead, status_code=201)
def create_item(
    payload: InventoryItemCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> InventoryItemRead:
    service = OperationsService(session)
    item = service.create_item(payload)
    return _item_read(service.get_item(item.id))


@warehouse.patch("/items/{item_id}", response_model=InventoryItemRead)
def update_item(
    item_id: str,
    payload: InventoryItemUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> InventoryItemRead:
    service = OperationsService(session)
    service.update_item(item_id, payload)
    return _item_read(service.get_item(item_id))


@warehouse.post("/items/{item_id}/movements", response_model=StockMovementRead, status_code=201)
def create_movement(
    item_id: str,
    payload: StockMovementCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> StockMovementRead:
    service = OperationsService(session)
    movement = service.move_stock(item_id, payload)
    movement.item = service.get_item(item_id)
    return _movement_read(movement)


@warehouse.get("/movements", response_model=list[StockMovementRead])
def list_movements(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    item_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StockMovementRead]:
    service = OperationsService(session)
    return [_movement_read(m) for m in service.list_movements(item_id=item_id, limit=limit, offset=offset)]


@warehouse.get("/alarms", response_model=list[InventoryAlarm])
def stock_alarms(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> list[InventoryAlarm]:
    """Stockout alarm (§3.1) with a suggested supplier per item."""
    service = OperationsService(session)
    alarms: list[InventoryAlarm] = []
    for item in service.low_stock_items():
        suggestions = service.supplier_suggestions(item_id=item.id)
        alarms.append(
            InventoryAlarm(
                item_id=item.id,
                name=item.name,
                kind=item.kind,
                kind_name=item.item_type.name,
                unit_name=item.item_unit.name,
                quantity=Decimal(item.quantity),
                min_quantity=Decimal(item.min_quantity),
                unit=item.unit,
                supplier_id=item.supplier_id,
                suggested_supplier=suggestions[0].name if suggestions else None,
            )
        )
    return alarms


@warehouse.get("/summary", response_model=InventorySummary)
def inventory_summary(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> InventorySummary:
    data = OperationsService(session).inventory_summary()
    return InventorySummary(
        other_count=data["other_count"],
        filament_count=data["filament_count"],
        product_count=data["product_count"],
        total_value=data["total_value"],
        low_stock_count=data["low_stock_count"],
        items=[_item_read(i) for i in data["items"]],
    )


# -------------------------------------------------------------------- orders ---
@orders.get("", response_model=list[OrderRead])
def list_orders(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    status: Annotated[str | None, Query()] = None,
    channel: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OrderRead]:
    service = OperationsService(session)
    return [
        _order_read(o)
        for o in service.list_orders(
            status=status,
            channel=channel,
            search=search,
            date_from=date_from,
            date_to=date_to,
            limit=limit, offset=offset,
        )
    ]


@orders.get("/summary", response_model=OrderSummary)
def order_summary(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> OrderSummary:
    return OrderSummary(**OperationsService(session).order_summary())


@orders.post("", response_model=OrderRead, status_code=201)
def create_order(
    payload: OrderCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> OrderRead:
    service = OperationsService(session)
    order = service.create_order(payload)
    return _order_read(service.get_order(order.id))


@orders.get("/reports/sales", response_model=SalesReport)
def sales_report(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    period: Annotated[str, Query(pattern="^(daily|weekly|monthly|annual)$")] = "monthly",
    date_from: Annotated[str | None, Query()] = None,
    date_to: Annotated[str | None, Query()] = None,
) -> SalesReport:
    today = date.fromisoformat(today_iso())
    default_from = {
        "daily": today - timedelta(days=30),
        "weekly": today - timedelta(weeks=12),
        "monthly": today - timedelta(days=365),
        "annual": today - timedelta(days=365 * 5),
    }[period]
    report = OperationsService(session).sales_report(
        period=period,
        start=date_from or default_from.isoformat(),
        end=date_to or today.isoformat(),
    )
    return SalesReport(**report)


@orders.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> OrderRead:
    return _order_read(OperationsService(session).get_order(order_id))


@orders.patch("/{order_id}", response_model=OrderRead)
def update_order(
    order_id: str,
    payload: OrderUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> OrderRead:
    service = OperationsService(session)
    service.update_order(order_id, payload)
    return _order_read(service.get_order(order_id))


@orders.get("/{order_id}/proforma.pdf")
def proforma_pdf(
    order_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> Response:
    """پیش‌فاکتور فروش — printable RTL PDF of one order (Jinja2 + WeasyPrint).

    WeasyPrint needs native Pango/Fontconfig/HarfBuzz; when it is missing (e.g. a dev box) the
    same HTML is returned so the browser's «چاپ → ذخیره به‌عنوان PDF» still works.
    """
    from ..services.pdf import PRINTABLE_HTML_CSP, render_html

    service = OperationsService(session)
    order = service.get_order(order_id)
    read = _order_read(order)
    context = {
        "company": {"name": "V.I.R.A", "tagline": "چاپ سه‌بعدی و فروش محصولات"},
        "order": {
            "order_number": read.order_number,
            "order_date": read.order_date,
            "order_date_jalali": _jalali(read.order_date),
            "customer": {
                "name": read.customer_name,
                "phone": read.customer_phone or "—",
                "address": read.customer_address or "—",
            },
            "lines": [
                {
                    "description": _variant_label(line.product_name, line.variant),
                    "quantity": _fa_num(line.quantity),
                    "unit_price": _fa_money(line.unit_price),
                    "line_total": _fa_money(line.quantity * line.unit_price),
                }
                for line in read.items
            ],
            "subtotal": _fa_money(read.total),
            "discount": _fa_money(Decimal(0)),
            "total": _fa_money(read.total),
        },
    }
    headers = {"Content-Disposition": f'inline; filename="proforma-{read.order_number}.pdf"'}
    try:
        return Response(content=request.app.state.pdf_renderer("proforma.html", context), media_type="application/pdf",
                        headers=headers)
    except Exception:  # noqa: BLE001 - no WeasyPrint/native libs → printable HTML
        return Response(content=render_html("proforma.html", context), media_type="text/html",
                        headers={
                            "Content-Disposition": f'inline; filename="proforma-{read.order_number}.html"',
                            # Override the SPA's self-only default font policy for
                            # this script-free, self-contained printable document.
                            "Content-Security-Policy": PRINTABLE_HTML_CSP,
                        })


def _variant_label(product_name: str, variant: str) -> str:
    return f"{product_name} (حلقه و زنجیر)" if variant == "chain" else product_name


_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa_group(value: Decimal, pattern: str) -> str:
    """Grouped number with Persian digits (fa_IR separators, ٫ decimal).

    Babel's fa_IR locale keeps Latin digits, so they are transliterated here —
    the same presentation-only rule the SPA's `faDigits` applies.
    """
    try:
        from babel.numbers import format_decimal

        # fa_IR keeps Latin digits and Latin separators unless the arabext
        # numbering system is requested — then digits are transliterated below.
        text = format_decimal(
            value, format=pattern, locale="fa_IR", numbering_system="arabext"
        )
    except Exception:  # noqa: BLE001 - Babel missing → plain grouping
        text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text.translate(_FA_DIGITS)


def _fa_money(value: Decimal | None) -> str:
    """Persian-grouped Toman, exact (fraction kept only when non-zero)."""
    decimal = Decimal(value or 0)
    pattern = "#,##0" if decimal == decimal.to_integral_value() else "#,##0.####"
    return _fa_group(decimal, pattern)


def _fa_num(value: Decimal | None) -> str:
    return _fa_money(value)


def _jalali(iso: str) -> str:
    try:
        import jdatetime

        d = date.fromisoformat(iso)
        return jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d")
    except Exception:  # noqa: BLE001 - the PDF still renders with the ISO date
        return iso


# ---------------------------------------------------------------- production ---
@production.get("/jobs", response_model=list[ProductionJobRead])
def list_jobs(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductionJobRead]:
    service = OperationsService(session)
    return [_job_read(session, j) for j in service.list_jobs(status=status, limit=limit, offset=offset)]


@production.post("/jobs", response_model=ProductionJobRead, status_code=201)
def create_job(
    payload: ProductionJobCreate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> ProductionJobRead:
    service = OperationsService(session)
    job = service.create_job(payload)
    return _job_read(session, job)


@production.get("/jobs/{job_id}", response_model=ProductionJobRead)
def get_job(
    job_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> ProductionJobRead:
    return _job_read(session, OperationsService(session).get_job(job_id))


@production.patch("/jobs/{job_id}", response_model=ProductionJobRead)
def update_job(
    job_id: str,
    payload: ProductionJobUpdate,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> ProductionJobRead:
    service = OperationsService(session)
    job = service.update_job(job_id, payload)
    return _job_read(session, job)


@production.post("/jobs/{job_id}/start", response_model=ProductionJobRead)
def start_job(
    job_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> ProductionJobRead:
    service = OperationsService(session)
    return _job_read(session, service.start_job(job_id))


@production.post("/jobs/{job_id}/finish", response_model=ProductionJobRead)
def finish_job(
    job_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> ProductionJobRead:
    """Consume filament from stock and add the produced models to stock."""
    service = OperationsService(session)
    return _job_read(session, service.finish_job(job_id))


@production.post("/jobs/{job_id}/cancel", response_model=ProductionJobRead)
def cancel_job(
    job_id: str,
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*WRITE_ROLES))],
) -> ProductionJobRead:
    service = OperationsService(session)
    return _job_read(session, service.cancel_job(job_id))


@production.get("/summary", response_model=ProductionSummary)
def production_summary(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles(*READ_ROLES))],
) -> ProductionSummary:
    service = OperationsService(session)
    data = service.production_summary()
    return ProductionSummary(
        planned=data["planned"],
        in_progress=data["in_progress"],
        done=data["done"],
        filament_grams_planned=data["filament_grams_planned"],
        jobs=[_job_read(session, j) for j in data["jobs"]],
    )

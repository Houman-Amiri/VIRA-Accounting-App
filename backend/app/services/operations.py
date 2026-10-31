"""Operations service — warehouse, orders and production rules (MASTER_PROMPT §3).

Key behaviours:

* **Stockout alarm** — an item is alarming when ``quantity <= min_quantity``.
* **Supplier suggestion** — suppliers are ranked by the mean of the user-given
  price/quality/delivery scores; the suggestion for an alarming item prefers
  the item's own supplier, else the best-scoring active one.
* **Stock ledger** — every quantity change writes an append-only
  ``stock_movements`` row and updates ``inventory_items.quantity`` atomically;
  stock can never go negative (``InsufficientStockError``).
* **Production** — finishing a job consumes ``filament_grams × quantity`` from
  the chosen filament spool and puts ``quantity`` produced models into stock.
* **Sales reports** — daily/weekly/monthly/annual aggregation over orders.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..ids import today_iso, utc_now_iso, uuid7
from ..models import (
    InventoryItem,
    Order,
    OrderItem,
    ProductionFilament,
    ProductionJob,
    StockMovement,
    Supplier,
)
from ..money import MAX_ABS_AMOUNT, plain_number
from ..schemas.catalog import CatalogDeletion
from ..schemas.operations import (
    Channel,
    InventoryItemCreate,
    InventoryItemUpdate,
    OrderCreate,
    OrderItemIn,
    OrderUpdate,
    PlannedJob,
    ProductionFilamentIn,
    ProductionFilamentRead,
    ProductionJobCreate,
    ProductionJobUpdate,
    StockMovementCreate,
    SupplierCreate,
    SupplierUpdate,
    Variant,
)
from .catalog import CatalogService
from .errors import (
    DomainError,
    InsufficientStockError,
    InvalidOperationsStateError,
    NotFoundError,
    StaleVersionError,
)
from .security_audit import record_security_event

# backwards-compatible alias kept for readability inside this module
InvalidOrderStateError = InvalidOperationsStateError


def _mean_score(supplier: Supplier) -> float:
    return (supplier.score_price + supplier.score_quality + supplier.score_delivery) / 3


class OperationsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------- suppliers ---
    def list_suppliers(self, *, active_only: bool = False) -> list[Supplier]:
        stmt = select(Supplier).order_by(Supplier.name)
        if active_only:
            stmt = stmt.where(Supplier.is_active == 1)
        return list(self.session.scalars(stmt))

    def get_supplier(self, supplier_id: str) -> Supplier:
        supplier = self.session.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError(f"supplier {supplier_id} not found")
        return supplier

    def create_supplier(self, data: SupplierCreate) -> Supplier:
        CatalogService(self.session).ensure_name(Supplier, data.name)
        now = utc_now_iso()
        supplier = Supplier(
            id=uuid7(),
            name=data.name,
            address=data.address,
            phone=data.phone,
            score_price=data.score_price,
            score_quality=data.score_quality,
            score_delivery=data.score_delivery,
            notes=data.notes,
            is_active=1,
            version_id=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(supplier)
        self.session.flush()
        return supplier

    def update_supplier(self, supplier_id: str, data: SupplierUpdate) -> Supplier:
        supplier = self.get_supplier(supplier_id)
        if supplier.version_id != data.version_id:
            raise StaleVersionError(
                f"supplier {supplier.name} was modified concurrently "
                f"(expected {data.version_id}, found {supplier.version_id})"
            )
        payload = data.model_dump(exclude={"version_id"}, exclude_unset=True)
        if "name" in payload:
            CatalogService(self.session).ensure_name(Supplier, payload["name"], exclude=supplier_id)
        if "is_active" in payload:
            supplier.is_active = 1 if payload.pop("is_active") else 0
        for field, value in payload.items():
            setattr(supplier, field, value)
        supplier.version_id += 1
        supplier.updated_at = utc_now_iso()
        self.session.flush()
        return supplier

    def supplier_suggestions(self, *, item_id: str | None = None) -> list[Supplier]:
        """Active suppliers ranked best-first (optionally for one item's kind)."""
        suppliers = [s for s in self.list_suppliers(active_only=True)]
        if item_id:
            item = self.get_item(item_id)
            linked = [s for s in suppliers if s.id == item.supplier_id]
            rest = [s for s in suppliers if s.id != item.supplier_id]
            return sorted(linked, key=_mean_score, reverse=True) + sorted(
                rest, key=_mean_score, reverse=True
            )
        return sorted(suppliers, key=_mean_score, reverse=True)

    # ------------------------------------------------------------- inventory ---
    def list_items(
        self,
        *,
        kind: str | None = None,
        search: str | None = None,
        low_only: bool = False,
        active_only: bool = True,
        limit: int | None = 500,
    ) -> list[InventoryItem]:
        stmt = select(InventoryItem).options(selectinload(InventoryItem.supplier))
        if active_only:
            stmt = stmt.where(InventoryItem.is_active == 1)
        if kind:
            stmt = stmt.where(InventoryItem.kind == kind)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    InventoryItem.name.ilike(like),
                    InventoryItem.color.ilike(like),
                    InventoryItem.notes.ilike(like),
                )
            )
        if low_only:
            stmt = stmt.where(InventoryItem.quantity <= InventoryItem.min_quantity)
        stmt = stmt.order_by(InventoryItem.kind, InventoryItem.name).limit(limit)
        return list(self.session.scalars(stmt))

    def get_item(self, item_id: str) -> InventoryItem:
        item = self.session.get(InventoryItem, item_id)
        if item is None:
            raise NotFoundError(f"inventory item {item_id} not found")
        return item

    def create_item(self, data: InventoryItemCreate) -> InventoryItem:
        CatalogService(self.session).validate_item(data.kind, data.unit, data.supplier_id)
        now = utc_now_iso()
        item = InventoryItem(
            id=uuid7(),
            name=data.name,
            kind=data.kind,
            color=data.color,
            unit=data.unit,
            quantity=Decimal(0),
            min_quantity=data.min_quantity,
            unit_price=data.unit_price,
            supplier_id=data.supplier_id,
            purchased_at=data.purchased_at,
            notes=data.notes,
            is_active=1,
            version_id=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        self.session.flush()
        if data.quantity and Decimal(data.quantity) > 0:
            self.move_stock(
                item.id,
                StockMovementCreate(
                    kind="IN",
                    quantity=data.quantity,
                    unit_cost=data.unit_price,
                    reason="initial",
                ),
            )
        return item

    def update_item(self, item_id: str, data: InventoryItemUpdate) -> InventoryItem:
        item = self.get_item(item_id)
        if item.version_id != data.version_id:
            raise StaleVersionError(
                f"item {item.name} was modified concurrently "
                f"(expected {data.version_id}, found {item.version_id})"
            )
        payload = data.model_dump(exclude={"version_id"}, exclude_unset=True)
        if payload.get("unit", item.unit) != item.unit:
            raise DomainError("واحد کالای ثبت‌شده قابل تغییر نیست؛ کالای جداگانه تعریف کنید")
        if "supplier_id" in payload and payload["supplier_id"] != item.supplier_id:
            supplier = self.get_supplier(payload["supplier_id"]) if payload["supplier_id"] is not None else None
            if supplier is not None and not supplier.is_active:
                raise DomainError("انتخاب تأمین‌کنندهٔ غیرفعال مجاز نیست")
        if "is_active" in payload:
            item.is_active = 1 if payload.pop("is_active") else 0
        for field, value in payload.items():
            setattr(item, field, value)
        if Decimal(item.quantity) * Decimal(item.unit_price) >= MAX_ABS_AMOUNT:
            raise DomainError("ارزش کالا از حد مجاز مبلغ دقیق بیشتر می‌شود")
        item.version_id += 1
        item.updated_at = utc_now_iso()
        self.session.flush()
        return item

    def delete_item(
        self, item_id: str, version_id: int, actor_id: str | None = None
    ) -> CatalogDeletion:
        """Remove a warehouse item, keeping history whenever it was ever used.

        An item with any stock movement, order line or production reference is
        deactivated instead of deleted: hard deletion would orphan the ledger of
        what was bought, produced and sold. A brand-new, never-touched item is
        deleted for real so a typo does not linger in the pickers.
        """
        item = self.get_item(item_id)
        if item.version_id != version_id:
            raise StaleVersionError(
                f"item {item.name} was modified concurrently "
                f"(expected {version_id}, found {item.version_id})"
            )
        used = bool(
            self.session.scalar(
                select(func.count()).select_from(StockMovement).where(
                    StockMovement.item_id == item_id,
                    # The opening balance is not "use": a mistyped new item must
                    # stay deletable, otherwise every typo becomes a dead row.
                    StockMovement.reason.is_distinct_from("initial"),
                )
            )
        ) or bool(
            self.session.scalar(
                select(func.count()).select_from(OrderItem).where(
                    OrderItem.inventory_item_id == item_id
                )
            )
        ) or bool(
            self.session.scalar(
                select(func.count()).select_from(ProductionJob).where(
                    or_(
                        ProductionJob.filament_item_id == item_id,
                        ProductionJob.product_item_id == item_id,
                    )
                )
            )
        ) or bool(
            self.session.scalar(
                select(func.count()).select_from(ProductionFilament).where(
                    ProductionFilament.filament_item_id == item_id
                )
            )
        )
        if used or Decimal(item.quantity) != 0:
            item.is_active = 0
            item.version_id += 1
            item.updated_at = utc_now_iso()
            self.session.flush()
            self._record_item_event(item, "deactivated", actor_id)
            return CatalogDeletion(
                action="deactivated",
                version_id=item.version_id,
                reason=(
                    "این کالا سابقهٔ گردش، سفارش یا تولید دارد؛ برای حفظ سوابق غیرفعال شد و "
                    "از فهرست‌ها حذف می‌شود. حذف فیزیکی انجام نشد."
                ),
            )
        self._record_item_event(item, "deleted", actor_id)
        self.session.delete(item)
        self.session.flush()
        return CatalogDeletion(
            action="deleted", reason="کالای استفاده‌نشده به‌طور کامل حذف شد."
        )

    def _record_item_event(self, item: InventoryItem, action: str, actor_id: str | None) -> None:
        record_security_event(
            self.session,
            "INVENTORY_ITEM_DELETED",
            actor_id=actor_id,
            detail={
                "id": item.id,
                "name": item.name,
                "action": action,
                "quantity": str(Decimal(item.quantity)),
                "version_id": item.version_id,
            },
        )

    def move_stock(self, item_id: str, data: StockMovementCreate) -> StockMovement:
        item = self.get_item(item_id)
        quantity = Decimal(data.quantity)
        if not item.is_active:
            raise DomainError("گردش برای کالای غیرفعال مجاز نیست")
        if data.kind in ("IN", "OUT") and quantity <= 0:
            raise DomainError("ورودی/خروجی انبار باید بزرگ‌تر از صفر باشد")
        if data.kind == "IN":
            item.quantity = Decimal(item.quantity) + quantity
        elif data.kind == "OUT":
            if Decimal(item.quantity) < quantity:
                raise InsufficientStockError(
                    f"«{item.name}»: موجودی کافی نیست "
                    f"(درخواست {quantity}، موجود {item.quantity})"
                )
            item.quantity = Decimal(item.quantity) - quantity
        else:  # ADJUST — set the counted quantity
            item.quantity = quantity
        if Decimal(item.quantity) >= MAX_ABS_AMOUNT:
            raise DomainError("موجودی از حد مجاز عدد دقیق بیشتر می‌شود")
        # Price stability: only an incoming purchase may re-price the item.
        # Production is an internal transfer — the product's warehouse price is
        # the owner's decision and finishing a job must never overwrite it
        # (v1.0.11 shipped a defect where starting/finishing production silently
        # replaced the unit price the owner had set in the warehouse).
        if (
            data.unit_cost is not None
            and data.kind == "IN"
            and data.reason != "production"
        ):
            item.unit_price = Decimal(data.unit_cost)
        if Decimal(item.quantity) * Decimal(item.unit_price) >= MAX_ABS_AMOUNT:
            raise DomainError("ارزش کالا از حد مجاز مبلغ دقیق بیشتر می‌شود")
        item.version_id += 1
        item.updated_at = utc_now_iso()
        movement = StockMovement(
            id=uuid7(),
            item_id=item.id,
            kind=data.kind,
            quantity=quantity,
            unit_cost=data.unit_cost,
            reason=data.reason,
            reference_id=data.reference_id,
            note=data.note,
            occurred_at=data.occurred_at or today_iso(),
            created_at=utc_now_iso(),
        )
        self.session.add(movement)
        self.session.flush()
        return movement

    def list_movements(self, *, item_id: str | None = None, limit: int = 200, offset: int = 0) -> list[StockMovement]:
        stmt = select(StockMovement).options(selectinload(StockMovement.item))
        if item_id:
            stmt = stmt.where(StockMovement.item_id == item_id)
        stmt = stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).offset(offset).limit(limit)
        return list(self.session.scalars(stmt))

    def low_stock_items(self) -> list[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .options(selectinload(InventoryItem.supplier))
            .where(
                InventoryItem.is_active == 1,
                InventoryItem.quantity <= InventoryItem.min_quantity,
            )
            .order_by(InventoryItem.name)
        )
        return list(self.session.scalars(stmt))

    def inventory_summary(self) -> dict[str, Any]:
        items = self.list_items(limit=None)
        total_value = sum((Decimal(i.quantity) * Decimal(i.unit_price) for i in items), Decimal(0))
        return {
            "other_count": sum(1 for i in items if i.kind not in {"FILAMENT", "PRODUCT"}),
            "filament_count": sum(1 for i in items if i.kind == "FILAMENT"),
            "product_count": sum(1 for i in items if i.kind == "PRODUCT"),
            "total_value": total_value,
            "low_stock_count": sum(
                1 for i in items if Decimal(i.quantity) <= Decimal(i.min_quantity)
            ),
            "items": items,
        }

    # ---------------------------------------------------------------- orders ---
    def next_order_number(self) -> int:
        current = self.session.scalar(select(func.max(Order.order_number))) or 0
        return int(current) + 1

    def next_job_number(self) -> int:
        current = self.session.scalar(select(func.max(ProductionJob.job_number))) or 0
        return int(current) + 1

    def list_orders(
        self,
        *,
        status: str | None = None,
        channel: str | None = None,
        search: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int | None = 200,
        offset: int = 0,
    ) -> list[Order]:
        stmt = select(Order).options(selectinload(Order.items))
        if status:
            stmt = stmt.where(Order.status == status)
        if channel:
            stmt = stmt.where(Order.channel == channel)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Order.customer_name.ilike(like),
                    Order.customer_phone.ilike(like),
                    Order.customer_address.ilike(like),
                )
            )
        if date_from:
            stmt = stmt.where(Order.order_date >= date_from)
        if date_to:
            stmt = stmt.where(Order.order_date <= date_to)
        stmt = stmt.order_by(Order.order_date.desc(), Order.order_number.desc()).offset(offset).limit(limit)
        return list(self.session.scalars(stmt))

    def order_summary(self) -> dict[str, int]:
        counts = dict(
            self.session.execute(select(Order.status, func.count()).group_by(Order.status)).all()
        )
        return {
            "total": sum(counts.values()),
            "new": counts.get("NEW", 0),
            "confirmed": counts.get("CONFIRMED", 0),
            "in_production": counts.get("IN_PRODUCTION", 0),
            "ready": counts.get("READY", 0),
            "delivered": counts.get("DELIVERED", 0),
            "shipped": counts.get("SHIPPED", 0),
            "cancelled": counts.get("CANCELLED", 0),
        }

    def get_order(self, order_id: str) -> Order:
        order = self.session.scalar(
            select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
        )
        if order is None:
            raise NotFoundError(f"order {order_id} not found")
        return order

    # ------------------------------------------------------- product recipe ---
    def _recipe_for(self, product_item_id: str | None) -> list[tuple[str, Decimal, Decimal]] | None:
        """Spools per produced model, taken from the newest finished job.

        Returns ``None`` when this product has never been produced here: the
        amount of filament is simply unknown, so callers warn instead of
        inventing a number or blocking a legitimate order.
        """
        if not product_item_id:
            return None
        job = self.session.scalar(
            select(ProductionJob)
            .options(selectinload(ProductionJob.filaments))
            .where(
                ProductionJob.product_item_id == product_item_id,
                ProductionJob.status == "DONE",
            )
            .order_by(ProductionJob.finished_at.desc(), ProductionJob.created_at.desc())
        )
        if job is None:
            return None
        rows = [
            (row.filament_item_id, Decimal(row.grams_per_unit), Decimal(row.unit_cost))
            for row in job.filaments
            if row.filament_item_id and Decimal(row.grams_per_unit) > 0
        ]
        if rows:
            return rows
        if job.filament_item_id and Decimal(job.filament_grams) > 0:
            item = self.session.get(InventoryItem, job.filament_item_id)
            price = Decimal(item.unit_price) if item is not None else Decimal(0)
            return [(job.filament_item_id, Decimal(job.filament_grams), price)]
        return None

    def _last_job_cost(self, product_item_id: str | None) -> Decimal:
        if not product_item_id:
            return Decimal(0)
        cost = self.session.scalar(
            select(ProductionJob.unit_cost)
            .where(
                ProductionJob.product_item_id == product_item_id,
                ProductionJob.status == "DONE",
            )
            .order_by(ProductionJob.finished_at.desc(), ProductionJob.created_at.desc())
        )
        return Decimal(cost) if cost is not None else Decimal(0)

    def _require_filament_available(
        self,
        recipe: list[tuple[str, Decimal, Decimal]],
        pieces: Decimal,
        *,
        product_name: str,
        reason: str,
    ) -> None:
        """Refuse a sale/production run the spools cannot cover."""
        shortages: list[str] = []
        for filament_item_id, grams_per_unit, _price in recipe:
            item = self.session.get(InventoryItem, filament_item_id)
            if item is None or not item.is_active:
                shortages.append("یکی از فیلامنت‌های این محصول در انبار نیست یا غیرفعال شده است")
                continue
            needed = grams_per_unit * pieces
            if Decimal(item.quantity) < needed:
                shortages.append(
                    f"«{item.name}»: نیاز {plain_number(needed)} گرم، موجود "
                    f"{plain_number(Decimal(item.quantity))} گرم"
                )
        if shortages:
            raise InsufficientStockError(
                f"{reason} «{product_name}»: فیلامنت کافی نیست — " + "؛ ".join(shortages)
            )

    def _warehouse_product(self, line: OrderItemIn) -> InventoryItem:
        if not line.inventory_item_id:
            raise DomainError(
                "هر ردیف سفارش باید یک محصول از انبار باشد؛ ابتدا محصول را در انبار ثبت کنید"
            )
        item = self.get_item(line.inventory_item_id)
        if item.kind != "PRODUCT" or item.unit != "PCS" or not item.is_active:
            raise DomainError(
                f"«{item.name}» محصول فعال انبار نیست و در سفارش قابل انتخاب نیست"
            )
        return item

    def _validate_order_lines(self, items: list[OrderItemIn]) -> None:
        """Only warehouse products are orderable; the rest is stock-dependent.

        A product that is not in the warehouse at all can never be ordered
        (item 7). A product that *is* in the warehouse but short of stock is
        allowed — the missing pieces go to production — and the shortage is
        reported as a warning. Ordering more than the spools can print is
        still refused (item 5), because that order could never be delivered.
        """
        for line in items:
            item = self._warehouse_product(line)
            pieces = Decimal(line.quantity)
            if pieces > Decimal(item.quantity):
                recipe = self._recipe_for(item.id)
                if recipe is not None:
                    self._require_filament_available(
                        recipe,
                        pieces,
                        product_name=item.name,
                        reason="ثبت سفارش ممکن نیست —",
                    )

    def _apply_items(self, order: Order, items: list[OrderItemIn]) -> None:
        self._validate_order_lines(items)
        priced: list[tuple[OrderItemIn, InventoryItem, Decimal, Decimal]] = []
        for line in items:
            item = self._warehouse_product(line)
            unit_price = Decimal(line.unit_price)
            unit_cost = Decimal(line.unit_cost)
            if unit_price <= 0:
                # The warehouse price is the catalogue price; the order only
                # snapshots it (v1.0.11 defect: production could re-price it).
                unit_price = Decimal(item.unit_price)
            if unit_cost <= 0:
                unit_cost = self._last_job_cost(item.id)
            priced.append((line, item, unit_price, unit_cost))
        amounts = [Decimal(line.quantity) * unit_price for line, _i, unit_price, _c in priced]
        costs = [Decimal(line.quantity) * unit_cost for line, _i, _p, unit_cost in priced]
        for total in (sum(amounts, Decimal(0)), sum(costs, Decimal(0))):
            if total >= MAX_ABS_AMOUNT:
                raise DomainError("جمع مبلغ سفارش از حد مجاز عدد دقیق بیشتر است")
        order.items.clear()
        for index, (line, item, unit_price, unit_cost) in enumerate(priced):
            order.items.append(
                OrderItem(
                    id=uuid7(),
                    order_id=order.id,
                    position=index,
                    product_name=(line.product_name or "").strip() or item.name,
                    variant=line.variant,
                    quantity=Decimal(line.quantity),
                    unit_price=unit_price,
                    unit_cost=unit_cost,
                    # Grams/hours are asked on the production job, not the order.
                    weight_g=Decimal(0),
                    print_hours=Decimal(0),
                    inventory_item_id=item.id,
                    notes=line.notes,
                )
            )
        self.session.flush()

    def create_order(self, data: OrderCreate) -> Order:
        now = utc_now_iso()
        order = Order(
            id=uuid7(),
            order_number=self.next_order_number(),
            order_date=data.order_date,
            customer_name=data.customer_name,
            customer_phone=data.customer_phone,
            customer_address=data.customer_address,
            status=data.status,
            channel=data.channel,
            notes=data.notes,
            version_id=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(order)
        self.session.flush()
        self._apply_items(order, data.items)
        return order

    def update_order(self, order_id: str, data: OrderUpdate) -> Order:
        order = self.get_order(order_id)
        if order.version_id != data.version_id:
            raise StaleVersionError(
                f"order #{order.order_number} was modified concurrently "
                f"(expected {data.version_id}, found {order.version_id})"
            )
        if order.status in ("SHIPPED", "DELIVERED", "CANCELLED") and not (
            order.status == "SHIPPED" and data.status == "DELIVERED" and
            data.model_fields_set <= {"version_id", "status"}
        ):
            raise InvalidOrderStateError("سفارش بسته یا ارسال‌شده قابل ویرایش نیست")
        jobs = self.order_linked_jobs(order.id)
        if jobs and (data.items is not None or data.channel is not None):
            raise InvalidOrderStateError("پس از اتصال تولید، تغییر ردیف‌ها یا کانال سفارش مجاز نیست")
        if data.status in {"CANCELLED", "READY", "SHIPPED", "DELIVERED"} and any(
            j.status in {"PLANNED", "IN_PROGRESS"} for j in jobs
        ):
            raise InvalidOrderStateError("ابتدا کارهای فعال تولید را پایان دهید یا لغو کنید")
        if data.status in {"READY", "SHIPPED", "DELIVERED"} and jobs:
            completed = {line.id: sum((Decimal(j.quantity) for j in jobs
                if j.order_item_id == line.id and j.status == "DONE"), Decimal(0))
                for line in order.items}
            if any(completed[line.id] < Decimal(line.quantity) for line in order.items):
                raise InvalidOrderStateError("تمام ردیف‌های سفارش هنوز تولید نشده‌اند")
        payload = data.model_dump(exclude={"version_id", "items"}, exclude_unset=True)
        for field, value in payload.items():
            setattr(order, field, value)
        if data.items is not None:
            self._apply_items(order, data.items)
        order.version_id += 1
        order.updated_at = utc_now_iso()
        self.session.flush()
        return order

    def plan_order_production(self, order_id: str) -> dict[str, Any]:
        """«افزودن به خط تولید» — plan jobs for every un-built order line.

        Validates the whole order first (spool availability for products whose
        composition is known), then creates the jobs, so a partial plan never
        half-succeeds. Lines without a known composition are still planned with
        a warning: the workshop must pick the spools on the production page,
        and finishing stays blocked until it does.
        """
        order = self.get_order(order_id)
        if order.status in {"CANCELLED", "SHIPPED", "DELIVERED"}:
            raise InvalidOrderStateError("سفارش بسته یا لغوشده قابل افزودن به خط تولید نیست")
        jobs = self.order_linked_jobs(order.id)
        active = {j.order_item_id for j in jobs if j.status in {"PLANNED", "IN_PROGRESS"}}
        done = {
            line.id: sum(
                (Decimal(j.quantity) for j in jobs if j.order_item_id == line.id and j.status == "DONE"),
                Decimal(0),
            )
            for line in order.items
        }
        plan: list[tuple[OrderItem, Decimal, list[ProductionFilamentIn] | None]] = []
        skipped: list[str] = []
        warnings: list[str] = []
        for line in order.items:
            remaining = Decimal(line.quantity) - done[line.id]
            if remaining <= 0:
                skipped.append(f"«{line.product_name}»: کامل تولید شده است")
                continue
            if line.id in active:
                skipped.append(f"«{line.product_name}»: کار تولید باز دارد")
                continue
            recipe = self._recipe_for(line.inventory_item_id)
            if recipe is None:
                warnings.append(
                    f"«{line.product_name}»: فرمول ساخت (فیلامنت‌ها) ثبت نشده است؛ "
                    "کار بدون فیلامنت برنامه‌ریزی می‌شود و تا انتخاب فیلامنت پایان نمی‌یابد."
                )
                plan.append((line, remaining, None))
                continue
            self._require_filament_available(
                recipe, remaining, product_name=line.product_name, reason="افزودن به خط تولید ممکن نیست —"
            )
            plan.append(
                (
                    line,
                    remaining,
                    [
                        ProductionFilamentIn(
                            filament_item_id=filament_item_id,
                            grams_per_unit=grams_per_unit,
                            unit_cost=price,
                        )
                        for filament_item_id, grams_per_unit, price in recipe
                    ],
                )
            )
        if not plan:
            raise InvalidOrderStateError(
                "برای این سفارش کار تولید جدیدی لازم نیست: " + "؛ ".join(skipped)
            )
        created: list[PlannedJob] = []
        for line, remaining, filaments in plan:
            job = self.create_job(
                ProductionJobCreate(
                    product_name=line.product_name,
                    quantity=remaining,
                    variant=cast(Variant, line.variant),
                    channel=cast(Channel, order.channel),
                    order_id=order.id,
                    order_item_id=line.id,
                    product_item_id=line.inventory_item_id,
                    filaments=filaments or [],
                    filament_grams=(
                        sum((row.grams_per_unit for row in filaments), Decimal(0))
                        if filaments
                        else Decimal(0)
                    ),
                    unit_cost=Decimal(line.unit_cost),
                    unit_price=Decimal(line.unit_price),
                    note=f"از سفارش #{order.order_number}",
                )
            )
            created.append(
                PlannedJob(
                    job_id=job.id,
                    job_number=job.job_number,
                    product_name=job.product_name,
                    quantity=Decimal(job.quantity),
                    filaments=[
                        ProductionFilamentRead(
                            id=row.id,
                            filament_item_id=row.filament_item_id,
                            filament_item_name=row.item.name if row.item is not None else None,
                            grams_per_unit=Decimal(row.grams_per_unit),
                            unit_cost=Decimal(row.unit_cost),
                            grams_total=Decimal(row.grams_per_unit) * Decimal(job.quantity),
                        )
                        for row in job.filaments
                    ],
                )
            )
        return {"created": created, "skipped": skipped, "warnings": warnings}

    def order_linked_jobs(self, order_id: str) -> list[ProductionJob]:
        return list(
            self.session.scalars(
                select(ProductionJob).where(ProductionJob.order_id == order_id)
            )
        )

    def set_order_status(self, order_id: str, status: str) -> Order:
        allowed = {
            "NEW", "CONFIRMED", "IN_PRODUCTION", "READY", "SHIPPED", "DELIVERED", "CANCELLED"
        }
        if status not in allowed:
            raise DomainError(f"unknown order status {status}")
        order = self.get_order(order_id)
        order.status = status
        order.version_id += 1
        order.updated_at = utc_now_iso()
        self.session.flush()
        return order

    # -------------------------------------------------------- sales reports ---
    def sales_report(
        self,
        *,
        period: str,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        """Aggregate orders into buckets — day/week/month/year (§3.2)."""
        if period not in ("daily", "weekly", "monthly", "annual"):
            raise DomainError(f"unknown report period {period}")
        orders = self.list_orders(date_from=start, date_to=end, limit=None)
        buckets: dict[str, dict[str, Any]] = {}

        def key_for(order_date: str) -> str:
            d = date.fromisoformat(order_date)
            if period == "daily":
                return order_date
            if period == "weekly":
                monday = d - timedelta(days=d.weekday())
                return monday.isoformat()
            if period == "monthly":
                return f"{d.year:04d}-{d.month:02d}"
            return f"{d.year:04d}"

        for order in orders:
            if order.status == "CANCELLED":
                continue
            bucket = buckets.setdefault(
                key_for(order.order_date),
                {"orders": 0, "quantity": Decimal(0), "revenue": Decimal(0), "cost": Decimal(0)},
            )
            bucket["orders"] += 1
            for line in order.items:
                quantity = Decimal(line.quantity)
                bucket["quantity"] += quantity
                bucket["revenue"] += quantity * Decimal(line.unit_price)
                bucket["cost"] += quantity * Decimal(line.unit_cost)

        rows = []
        for key in sorted(buckets):
            bucket = buckets[key]
            profit = bucket["revenue"] - bucket["cost"]
            rows.append({"period": key, **bucket, "profit": profit})
        totals = {
            "orders": sum(r["orders"] for r in rows),
            "quantity": sum((r["quantity"] for r in rows), Decimal(0)),
            "revenue": sum((r["revenue"] for r in rows), Decimal(0)),
            "cost": sum((r["cost"] for r in rows), Decimal(0)),
            "profit": sum((r["profit"] for r in rows), Decimal(0)),
        }
        return {"period": period, "start": start, "end": end, **totals, "rows": rows}

    # ------------------------------------------------------------ production ---
    def list_jobs(
        self, *, status: str | None = None, limit: int | None = 200, offset: int = 0
    ) -> list[ProductionJob]:
        stmt = select(ProductionJob)
        if status:
            stmt = stmt.where(ProductionJob.status == status)
        stmt = stmt.order_by(ProductionJob.created_at.desc(), ProductionJob.id.desc()).offset(offset).limit(limit)
        return list(self.session.scalars(stmt))

    def get_job(self, job_id: str) -> ProductionJob:
        job = self.session.get(ProductionJob, job_id)
        if job is None:
            raise NotFoundError(f"production job {job_id} not found")
        return job

    def job_components(self, job: ProductionJob) -> list[ProductionFilament]:
        return list(job.filaments)

    def _set_components(
        self, job: ProductionJob, filaments: list[ProductionFilamentIn]
    ) -> None:
        """Replace the spool list and keep the legacy total in step."""
        job.filaments.clear()
        total = Decimal(0)
        for index, row in enumerate(filaments):
            item = self.get_item(row.filament_item_id)
            if item.kind != "FILAMENT" or item.unit != "G" or not item.is_active:
                raise DomainError(
                    f"«{item.name}» فیلامنت فعال با واحد گرم نیست و در تولید قابل انتخاب نیست"
                )
            grams = Decimal(row.grams_per_unit)
            if grams <= 0:
                raise DomainError("گرم هر عدد برای هر فیلامنت باید بزرگ‌تر از صفر باشد")
            price = Decimal(row.unit_cost) if row.unit_cost is not None else Decimal(item.unit_price)
            job.filaments.append(
                ProductionFilament(
                    id=uuid7(),
                    job_id=job.id,
                    position=index,
                    filament_item_id=item.id,
                    grams_per_unit=grams,
                    unit_cost=price,
                    created_at=utc_now_iso(),
                )
            )
            total += grams
        self.session.flush()
        if job.filaments:
            job.filament_item_id = job.filaments[0].filament_item_id
            job.filament_grams = total
        else:
            job.filament_item_id = None
            job.filament_grams = Decimal(0)

    def _validate_job(self, job: ProductionJobCreate | ProductionJob, *, finishing: bool = False) -> None:
        if job.order_item_id and not job.order_id:
            raise DomainError("ردیف سفارش بدون انتخاب سفارش معتبر نیست")
        if job.order_id:
            order = self.get_order(job.order_id)
            if order.status in {"CANCELLED", "SHIPPED", "DELIVERED"}:
                raise InvalidOrderStateError("سفارش بسته یا ارسال‌شده قابل تولید نیست")
            line = next((line for line in order.items if line.id == job.order_item_id), None)
            if line is None:
                raise DomainError("ردیف تولید باید متعلق به همین سفارش باشد")
            others = self.order_linked_jobs(order.id)
            reserved = sum((Decimal(j.quantity) for j in others
                if j.id != getattr(job, "id", None) and j.order_item_id == line.id
                and j.status != "CANCELLED"), Decimal(0))
            if reserved + Decimal(job.quantity) > Decimal(line.quantity):
                raise DomainError("مقدار تولید از تعداد باقی‌ماندهٔ ردیف سفارش بیشتر است")
        grams = Decimal(job.filament_grams) * Decimal(job.quantity)
        if grams >= MAX_ABS_AMOUNT:
            raise DomainError("وزن کل تولید از حد مجاز بیشتر است")
        if grams != grams.quantize(Decimal("0.0001")):
            raise DomainError("حاصل وزن هر عدد × تعداد باید حداکثر چهار رقم اعشار داشته باشد")
        for item_id, kind, unit in [(job.filament_item_id, "FILAMENT", "G"),
                                    (job.product_item_id, "PRODUCT", "PCS")]:
            if item_id:
                item = self.get_item(item_id)
                if item.kind != kind or item.unit != unit or not item.is_active:
                    raise DomainError("نوع، واحد یا فعال‌بودن کالای متصل به تولید معتبر نیست")
        components = getattr(job, "filaments", [])
        component_ids = [row.filament_item_id for row in components]
        if len(component_ids) != len(set(component_ids)):
            raise DomainError("هر فیلامنت فقط یک بار در یک کار تولید قابل انتخاب است")
        for row in components:
            if Decimal(row.grams_per_unit) <= 0:
                raise DomainError("گرم هر عدد برای هر فیلامنت باید بزرگ‌تر از صفر باشد")
            if not row.filament_item_id:
                raise DomainError("فیلامنت هر ردیف مصرف را انتخاب کنید")
            item = self.get_item(row.filament_item_id)
            if item.kind != "FILAMENT" or item.unit != "G" or not item.is_active:
                raise DomainError("نوع، واحد یا فعال‌بودن کالای متصل به تولید معتبر نیست")
            component_total = Decimal(row.grams_per_unit) * Decimal(job.quantity)
            if not component_total.is_finite() or component_total >= MAX_ABS_AMOUNT:
                raise DomainError("وزن کل تولید از حد مجاز بیشتر است")
        if finishing and not job.product_item_id:
            raise DomainError("برای پایان تولید، محصول مقصد را مشخص کنید")
        has_filament = bool(components) or bool(job.filament_item_id and grams > 0)
        if finishing and not has_filament:
            raise DomainError(
                "برای پایان تولید، فیلامنت‌های مصرفی و وزن مثبت هر عدد را مشخص کنید"
            )

    def create_job(self, data: ProductionJobCreate) -> ProductionJob:
        self._validate_job(data)
        now = utc_now_iso()
        job = ProductionJob(
            id=uuid7(),
            job_number=self.next_job_number(),
            order_id=data.order_id,
            order_item_id=data.order_item_id,
            product_name=data.product_name,
            variant=data.variant,
            channel=data.channel,
            quantity=Decimal(data.quantity),
            status="PLANNED",
            filament_item_id=data.filament_item_id,
            product_item_id=data.product_item_id,
            filament_grams=Decimal(data.filament_grams),
            print_hours=Decimal(data.print_hours),
            unit_cost=Decimal(data.unit_cost),
            unit_price=Decimal(data.unit_price),
            note=data.note,
            started_at=None,
            finished_at=None,
            version_id=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        self.session.flush()
        if data.filaments:
            self._set_components(job, data.filaments)
        self._sync_order_status(job)
        return job

    def update_job(self, job_id: str, data: ProductionJobUpdate) -> ProductionJob:
        job = self.get_job(job_id)
        if job.version_id != data.version_id:
            raise StaleVersionError(
                f"production job #{job.job_number} was modified concurrently "
                f"(expected {data.version_id}, found {job.version_id})"
            )
        if job.status in ("DONE", "CANCELLED"):
            raise InvalidOrderStateError(
                f"کار تولید #{job.job_number} بسته شده است و قابل ویرایش نیست"
            )
        payload = data.model_dump(exclude={"version_id", "filaments"}, exclude_unset=True)
        for field, value in payload.items():
            setattr(job, field, value)
        if data.filaments is not None:
            self._set_components(job, data.filaments)
        self._validate_job(job)
        job.version_id += 1
        job.updated_at = utc_now_iso()
        self.session.flush()
        return job

    def start_job(self, job_id: str) -> ProductionJob:
        job = self.get_job(job_id)
        if job.status != "PLANNED":
            raise InvalidOrderStateError(f"job #{job.job_number} is {job.status}, not PLANNED")
        self._validate_job(job)
        job.status = "IN_PROGRESS"
        job.started_at = utc_now_iso()
        job.version_id += 1
        job.updated_at = utc_now_iso()
        self.session.flush()
        self._sync_order_status(job)
        return job

    def finish_job(self, job_id: str) -> ProductionJob:
        """Consume filament from stock and put the produced goods into stock."""
        job = self.get_job(job_id)
        if job.status not in ("PLANNED", "IN_PROGRESS"):
            raise InvalidOrderStateError(f"job #{job.job_number} is {job.status}")
        # Validate BOTH stock legs before writing either one. get_db rolls back
        # the whole transaction on failure; BEGIN IMMEDIATE serializes finishers.
        self._validate_job(job, finishing=True)
        quantity = Decimal(job.quantity)
        grams = Decimal(job.filament_grams)
        components = list(job.filaments)
        if components:
            # Check every spool BEFORE writing any movement: a half-consumed job
            # must never leave stock inconsistent.
            shortages = []
            for row in components:
                item = self.get_item(row.filament_item_id) if row.filament_item_id else None
                need = Decimal(row.grams_per_unit) * quantity
                have = Decimal(item.quantity) if item is not None else Decimal(0)
                if item is None or not item.is_active:
                    shortages.append("فیلامنت این کار در انبار نیست یا غیرفعال شده است")
                elif have < need:
                    shortages.append(
                        f"«{item.name}»: نیاز {plain_number(need)} گرم، موجود {plain_number(have)} گرم"
                    )
            if shortages:
                raise InsufficientStockError(
                    "پایان تولید ممکن نیست — فیلامنت کافی نیست: " + "؛ ".join(shortages)
                )
            for row in components:
                if not row.filament_item_id:
                    continue
                self.move_stock(
                    row.filament_item_id,
                    StockMovementCreate(
                        kind="OUT",
                        quantity=Decimal(row.grams_per_unit) * quantity,
                        reason="production",
                        reference_id=job.id,
                        note=f"کار تولید #{job.job_number}",
                    ),
                )
        elif job.filament_item_id and grams > 0:
            self.move_stock(
                job.filament_item_id,
                StockMovementCreate(
                    kind="OUT",
                    quantity=grams * quantity,
                    reason="production",
                    reference_id=job.id,
                    note=f"کار تولید #{job.job_number}",
                ),
            )
        if job.product_item_id:
            self.move_stock(
                job.product_item_id,
                StockMovementCreate(
                    kind="IN",
                    quantity=quantity,
                    reason="production",
                    reference_id=job.id,
                    note=f"کار تولید #{job.job_number}",
                    unit_cost=Decimal(job.unit_cost) if job.unit_cost else None,
                ),
            )
        now = utc_now_iso()
        job.status = "DONE"
        job.finished_at = now
        job.started_at = job.started_at or now
        job.version_id += 1
        job.updated_at = now
        self.session.flush()
        self._sync_order_status(job)
        return job

    def cancel_job(self, job_id: str) -> ProductionJob:
        job = self.get_job(job_id)
        if job.status in {"DONE", "CANCELLED"}:
            raise InvalidOrderStateError(f"job #{job.job_number} is already {job.status}")
        job.status = "CANCELLED"
        job.version_id += 1
        job.updated_at = utc_now_iso()
        self.session.flush()
        self._sync_order_status(job)
        return job

    def _sync_order_status(self, job: ProductionJob) -> None:
        """Keep the linked order's status in step with its production jobs."""
        if not job.order_id:
            return
        order = self.session.get(Order, job.order_id)
        if order is None or order.status in ("SHIPPED", "DELIVERED", "CANCELLED"):
            return
        jobs = [j for j in self.order_linked_jobs(order.id) if j.status != "CANCELLED"]
        completed = {line.id: sum((Decimal(j.quantity) for j in jobs
            if j.order_item_id == line.id and j.status == "DONE"), Decimal(0))
            for line in order.items}
        if order.items and not any(j.status in {"PLANNED", "IN_PROGRESS"} for j in jobs) and all(completed[line.id] >= Decimal(line.quantity) for line in order.items):
            order.status = "READY"
        elif any(j.status in {"IN_PROGRESS", "DONE"} for j in jobs):
            order.status = "IN_PRODUCTION"
        else:
            order.status = "CONFIRMED"
        order.version_id += 1
        order.updated_at = utc_now_iso()

    def production_summary(self) -> dict[str, Any]:
        jobs = self.list_jobs(limit=None)
        planned = [j for j in jobs if j.status == "PLANNED"]
        in_progress = [j for j in jobs if j.status == "IN_PROGRESS"]
        done = [j for j in jobs if j.status == "DONE"]
        grams = sum(
            (Decimal(j.filament_grams) * Decimal(j.quantity) for j in planned + in_progress),
            Decimal(0),
        )
        return {
            "planned": len(planned),
            "in_progress": len(in_progress),
            "done": len(done),
            "filament_grams_planned": grams,
            "jobs": (planned + in_progress + done)[:200],
        }

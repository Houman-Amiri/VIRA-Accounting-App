"""Pydantic v2 schemas for the operations domain (warehouse/orders/production).

Money and quantities travel as fixed-scale strings ("1250.5000") exactly like
the ledger API, so the client's decimal.js never sees a float.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from .catalog import clean_name

Amount = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]
# Derived inventory values multiply two scaled-four inputs; preserve all 8 places.
InventoryValue = Annotated[Decimal, Field(max_digits=26, decimal_places=8)]

ItemKind = Annotated[str, Field(min_length=1, max_length=100)]
ItemUnit = Annotated[str, Field(min_length=1, max_length=100)]
MovementKind = Literal["IN", "OUT", "ADJUST"]
OrderStatus = Literal[
    "NEW", "CONFIRMED", "IN_PRODUCTION", "READY", "SHIPPED", "DELIVERED", "CANCELLED"
]
Channel = Literal["direct", "marketplace"]
Variant = Literal["plain", "chain"]
ProductionStatus = Literal["PLANNED", "IN_PROGRESS", "DONE", "CANCELLED"]


# ----------------------------------------------------------------- suppliers ---
class SupplierBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=50)
    score_price: int = Field(default=50, ge=0, le=100)
    score_quality: int = Field(default=50, ge=0, le=100)
    score_delivery: int = Field(default=50, ge=0, le=100)
    notes: str | None = None


class SupplierCreate(SupplierBase):
    _clean_name = field_validator("name")(clean_name)


class SupplierUpdate(BaseModel):
    version_id: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = None
    phone: str | None = None
    score_price: int | None = Field(default=None, ge=0, le=100)
    score_quality: int | None = Field(default=None, ge=0, le=100)
    score_delivery: int | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    is_active: bool | None = None


    @field_validator('name', 'score_price', 'score_quality', 'score_delivery', 'is_active', mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("مقدار این فیلد نمی‌تواند null باشد")
        return value


    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return clean_name(value) if value is not None else value


class SupplierRead(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    is_active: bool
    version_id: int
    created_at: str
    updated_at: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def score(self) -> float:
        """Overall score = mean of the three user-given scores (§3.1)."""
        return round((self.score_price + self.score_quality + self.score_delivery) / 3, 1)


# ---------------------------------------------------------------- inventory ---
class InventoryItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: ItemKind = "FILAMENT"
    color: str | None = Field(default=None, max_length=50)
    unit: ItemUnit = "G"
    min_quantity: Amount = Field(default=Decimal(0), ge=0)
    unit_price: Amount = Field(default=Decimal(0), ge=0)
    supplier_id: str | None = None
    purchased_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = None


class InventoryItemCreate(InventoryItemBase):
    quantity: Amount = Field(default=Decimal(0), ge=0)


class InventoryItemUpdate(BaseModel):
    version_id: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = None
    unit: ItemUnit | None = None
    min_quantity: Amount | None = Field(default=None, ge=0)
    unit_price: Amount | None = Field(default=None, ge=0)
    supplier_id: str | None = None
    purchased_at: str | None = None
    notes: str | None = None
    is_active: bool | None = None


    @field_validator('name', 'unit', 'min_quantity', 'unit_price', 'is_active', mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("مقدار این فیلد نمی‌تواند null باشد")
        return value


class InventoryItemRead(InventoryItemBase):
    id: str
    quantity: Amount
    is_active: bool
    version_id: int
    created_at: str
    updated_at: str
    kind_name: str = ""
    unit_name: str = ""
    supplier_name: str | None = None
    low_stock: bool = False
    value: InventoryValue = Decimal(0)


class StockMovementCreate(BaseModel):
    kind: MovementKind
    # IN/OUT must be > 0 (enforced in the service); ADJUST records the counted
    # quantity and may legitimately be zero.
    quantity: Amount = Field(ge=0)
    unit_cost: Amount | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=100)
    reference_id: str | None = None
    note: str | None = None
    occurred_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class StockMovementRead(BaseModel):
    id: str
    item_id: str
    item_name: str
    kind: MovementKind
    quantity: Amount
    unit_cost: Amount | None
    reason: str | None
    reference_id: str | None
    note: str | None
    occurred_at: str
    created_at: str


class InventoryAlarm(BaseModel):
    kind_name: str = ""
    unit_name: str = ""
    item_id: str
    name: str
    kind: ItemKind
    quantity: Amount
    min_quantity: Amount
    unit: ItemUnit
    supplier_id: str | None
    suggested_supplier: str | None


class InventorySummary(BaseModel):
    other_count: int = 0
    filament_count: int
    product_count: int
    total_value: InventoryValue
    low_stock_count: int
    items: list[InventoryItemRead]


# ------------------------------------------------------------------- orders ---
class OrderItemIn(BaseModel):
    """A line the user writes on the order page.

    The product is chosen from the warehouse (``inventory_item_id``); its name
    defaults to that item's name. Grams and print hours are no longer asked on
    the order page (item 3) — they belong to the production job.
    """

    product_name: str = Field(default="", max_length=200)
    variant: Variant = "plain"
    quantity: Amount = Field(gt=0)
    unit_price: Amount = Field(default=Decimal(0), ge=0)
    unit_cost: Amount = Field(default=Decimal(0), ge=0)
    inventory_item_id: str | None = None
    notes: str | None = None


class OrderItemRead(BaseModel):
    id: str
    position: int
    product_name: str
    variant: Variant
    quantity: Amount
    unit_price: Amount
    unit_cost: Amount
    # Kept for reading orders saved before item 3; new lines store zero.
    weight_g: Amount = Decimal(0)
    print_hours: Amount = Decimal(0)
    inventory_item_id: str | None = None
    inventory_item_name: str | None = None
    notes: str | None = None


class OrderCreate(BaseModel):
    order_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=50)
    customer_address: str | None = Field(default=None, max_length=500)
    status: OrderStatus = "NEW"
    channel: Channel = "direct"
    notes: str | None = None
    items: list[OrderItemIn] = Field(min_length=1)


class OrderUpdate(BaseModel):
    version_id: int
    order_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    customer_name: str | None = Field(default=None, min_length=1, max_length=200)
    customer_phone: str | None = None
    customer_address: str | None = None
    status: OrderStatus | None = None
    channel: Channel | None = None
    notes: str | None = None
    items: list[OrderItemIn] | None = Field(default=None, min_length=1)


    @field_validator('order_date', 'customer_name', 'status', 'channel', 'items', mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("مقدار این فیلد نمی‌تواند null باشد")
        return value


class OrderRead(BaseModel):
    id: str
    order_number: int
    order_date: str
    customer_name: str
    customer_phone: str | None
    customer_address: str | None
    status: OrderStatus
    channel: Channel
    notes: str | None
    version_id: int
    created_at: str
    updated_at: str
    items: list[OrderItemRead]
    total: Amount
    total_cost: Amount
    profit: Amount
    # «کمبود موجودی» notices; the order is saved, production covers the gap.
    warnings: list[str] = Field(default_factory=list)


class SalesReportRow(BaseModel):
    period: str
    orders: int
    quantity: Amount
    revenue: Amount
    cost: Amount
    profit: Amount


class SalesReport(BaseModel):
    period: str
    start: str
    end: str
    orders: int
    quantity: Amount
    revenue: Amount
    cost: Amount
    profit: Amount
    rows: list[SalesReportRow]


# --------------------------------------------------------------- production ---
class ProductionFilamentIn(BaseModel):
    """One spool consumed by a job, with its own grams and price per gram."""

    filament_item_id: str
    grams_per_unit: Amount = Field(gt=0)
    # Absent price means "use the spool's current warehouse price" (snapshot).
    unit_cost: Amount | None = Field(default=None, ge=0)


class ProductionFilamentRead(BaseModel):
    id: str
    filament_item_id: str | None
    filament_item_name: str | None
    grams_per_unit: Amount
    unit_cost: Amount
    grams_total: Amount


class ProductionJobCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    quantity: Amount = Field(gt=0)
    variant: Variant = "plain"
    channel: Channel = "direct"
    order_id: str | None = None
    order_item_id: str | None = None
    filament_item_id: str | None = None
    product_item_id: str | None = None
    filament_grams: Amount = Field(default=Decimal(0), ge=0)
    filaments: list[ProductionFilamentIn] = Field(default_factory=list, max_length=20)
    print_hours: Amount = Field(default=Decimal(0), ge=0)
    unit_cost: Amount = Field(default=Decimal(0), ge=0)
    unit_price: Amount = Field(default=Decimal(0), ge=0)
    note: str | None = None

    @field_validator("filaments")
    @classmethod
    def distinct_spools(cls, value: list[ProductionFilamentIn]) -> list[ProductionFilamentIn]:
        ids = [row.filament_item_id for row in value]
        if len(ids) != len(set(ids)):
            raise ValueError("هر فیلامنت فقط یک بار در یک کار تولید قابل انتخاب است")
        return value


class ProductionJobUpdate(BaseModel):
    version_id: int
    order_item_id: str | None = None
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: Amount | None = Field(default=None, gt=0)
    variant: Variant | None = None
    channel: Channel | None = None
    filament_item_id: str | None = None
    product_item_id: str | None = None
    filament_grams: Amount | None = Field(default=None, ge=0)
    filaments: list[ProductionFilamentIn] | None = Field(default=None, max_length=20)
    print_hours: Amount | None = Field(default=None, ge=0)
    unit_cost: Amount | None = Field(default=None, ge=0)
    unit_price: Amount | None = Field(default=None, ge=0)
    note: str | None = None


    @field_validator('product_name', 'quantity', 'variant', 'channel', 'filament_grams', 'print_hours', 'unit_cost', 'unit_price', mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("مقدار این فیلد نمی‌تواند null باشد")
        return value


class ProductionJobRead(BaseModel):
    id: str
    job_number: int
    order_id: str | None
    order_number: int | None
    order_item_id: str | None
    product_name: str
    variant: Variant
    channel: Channel
    quantity: Amount
    status: ProductionStatus
    filament_item_id: str | None
    filament_item_name: str | None
    product_item_id: str | None
    product_item_name: str | None
    filament_grams: Amount
    filaments: list[ProductionFilamentRead] = Field(default_factory=list)
    filament_ready: bool = False
    print_hours: Amount
    unit_cost: Amount
    unit_price: Amount
    note: str | None
    started_at: str | None
    finished_at: str | None
    version_id: int
    created_at: str
    updated_at: str


class ProductionSummary(BaseModel):
    planned: int
    in_progress: int
    done: int
    filament_grams_planned: Amount
    jobs: list[ProductionJobRead]


class PlannedJob(BaseModel):
    job_id: str
    job_number: int
    product_name: str
    quantity: Amount
    filaments: list[ProductionFilamentRead] = Field(default_factory=list)


class OrderProductionResult(BaseModel):
    """Outcome of «افزودن به خط تولید» — created jobs plus honest warnings."""

    created: list[PlannedJob] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OrderSummary(BaseModel):
    """Counts across all orders, independent of the recent-orders page limit."""

    total: int
    new: int
    confirmed: int
    in_production: int
    ready: int
    delivered: int
    shipped: int
    cancelled: int

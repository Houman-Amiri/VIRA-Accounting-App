"""Pydantic v2 schemas for the operations domain (warehouse/orders/production).

Money and quantities travel as fixed-scale strings ("1250.5000") exactly like
the ledger API, so the client's decimal.js never sees a float.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

Amount = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]

ItemKind = Literal["FILAMENT", "PRODUCT"]
ItemUnit = Literal["G", "PCS"]
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
    pass


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
    min_quantity: Amount = Decimal(0)
    unit_price: Amount = Decimal(0)
    supplier_id: str | None = None
    purchased_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str | None = None


class InventoryItemCreate(InventoryItemBase):
    quantity: Amount = Decimal(0)


class InventoryItemUpdate(BaseModel):
    version_id: int
    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = None
    unit: ItemUnit | None = None
    min_quantity: Amount | None = None
    unit_price: Amount | None = None
    supplier_id: str | None = None
    purchased_at: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class InventoryItemRead(InventoryItemBase):
    id: str
    quantity: Amount
    is_active: bool
    version_id: int
    created_at: str
    updated_at: str
    supplier_name: str | None = None
    low_stock: bool = False
    value: Amount = Decimal(0)


class StockMovementCreate(BaseModel):
    kind: MovementKind
    # IN/OUT must be > 0 (enforced in the service); ADJUST records the counted
    # quantity and may legitimately be zero.
    quantity: Amount = Field(ge=0)
    unit_cost: Amount | None = None
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
    item_id: str
    name: str
    kind: ItemKind
    quantity: Amount
    min_quantity: Amount
    unit: ItemUnit
    supplier_id: str | None
    suggested_supplier: str | None


class InventorySummary(BaseModel):
    filament_count: int
    product_count: int
    total_value: Amount
    low_stock_count: int
    items: list[InventoryItemRead]


# ------------------------------------------------------------------- orders ---
class OrderItemIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    variant: Variant = "plain"
    quantity: Amount = Field(gt=0)
    unit_price: Amount = Decimal(0)
    unit_cost: Amount = Decimal(0)
    weight_g: Amount = Decimal(0)
    print_hours: Amount = Decimal(0)
    inventory_item_id: str | None = None
    notes: str | None = None


class OrderItemRead(OrderItemIn):
    id: str
    position: int


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
    items: list[OrderItemIn] | None = None


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
class ProductionJobCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    quantity: Amount = Field(gt=0)
    variant: Variant = "plain"
    channel: Channel = "direct"
    order_id: str | None = None
    order_item_id: str | None = None
    filament_item_id: str | None = None
    product_item_id: str | None = None
    filament_grams: Amount = Decimal(0)
    print_hours: Amount = Decimal(0)
    unit_cost: Amount = Decimal(0)
    unit_price: Amount = Decimal(0)
    note: str | None = None


class ProductionJobUpdate(BaseModel):
    version_id: int
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: Amount | None = Field(default=None, gt=0)
    variant: Variant | None = None
    channel: Channel | None = None
    filament_item_id: str | None = None
    product_item_id: str | None = None
    filament_grams: Amount | None = None
    print_hours: Amount | None = None
    unit_cost: Amount | None = None
    unit_price: Amount | None = None
    note: str | None = None


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

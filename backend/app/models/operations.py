"""Operations domain (MASTER_PROMPT §3.1–§3.3) — warehouse, orders, production.

The 3D-printing business core: filament/produced-goods inventory with stockout
alarms and supplier scoring, customer orders with line items, and production
jobs that consume warehouse filament and put produced models back into stock.

Storage follows the project-wide rules: ``TEXT`` UUIDv7 ids, ISO ``TEXT``
dates/timestamps, ``INTEGER`` 0/1 booleans, quantities and money as scaled
``INTEGER`` (×10 000) through :class:`~app.db_types.ScaledMoneyType`, and
non-negative CHECKs on every amount.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db_types import ScaledMoneyType
from .base import Base, TimestampMixin

ITEM_KINDS = ("FILAMENT", "PRODUCT")
ITEM_UNITS = ("G", "PCS")
MOVEMENT_KINDS = ("IN", "OUT", "ADJUST")
ORDER_STATUSES = (
    "NEW",
    "CONFIRMED",
    "IN_PRODUCTION",
    "READY",
    "SHIPPED",
    "DELIVERED",
    "CANCELLED",
)
ORDER_CHANNELS = ("direct", "marketplace")
PRODUCTION_STATUSES = ("PLANNED", "IN_PROGRESS", "DONE", "CANCELLED")
VARIANTS = ("plain", "chain")


class Supplier(Base, TimestampMixin):
    """Supplier with the user-given price/quality/delivery scores (§3.1)."""

    __tablename__ = "suppliers"
    __table_args__ = (
        CheckConstraint("is_active IN (0,1)", name="is_active"),
        CheckConstraint("score_price BETWEEN 0 AND 100", name="score_price"),
        CheckConstraint("score_quality BETWEEN 0 AND 100", name="score_quality"),
        CheckConstraint("score_delivery BETWEEN 0 AND 100", name="score_delivery"),
        Index("ix_suppliers_name", "name"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_price: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    score_quality: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    score_delivery: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    items: Mapped[list[InventoryItem]] = relationship(back_populates="supplier")


class InventoryItem(Base, TimestampMixin):
    """Filament spool or produced model held in the warehouse (§3.1)."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("kind IN ('FILAMENT','PRODUCT')", name="kind"),
        CheckConstraint("unit IN ('G','PCS')", name="unit"),
        CheckConstraint("is_active IN (0,1)", name="is_active"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("min_quantity >= 0", name="min_quantity_non_negative"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index("ix_inventory_items_kind", "kind", "is_active"),
        Index("ix_inventory_items_supplier", "supplier_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="FILAMENT")
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(Text, nullable=False, default="G")
    quantity: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False, default=Decimal(0))
    min_quantity: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    unit_price: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    supplier_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    purchased_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    supplier: Mapped[Supplier | None] = relationship(back_populates="items")
    movements: Mapped[list[StockMovement]] = relationship(back_populates="item")


class StockMovement(Base):
    """Append-only stock ledger (IN purchases, OUT consumption, ADJUST counts)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("kind IN ('IN','OUT','ADJUST')", name="kind"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_stock_movements_item", "item_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    item_id: Mapped[str] = mapped_column(
        Text, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(ScaledMoneyType, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    item: Mapped[InventoryItem] = relationship(back_populates="movements")


class Order(Base, TimestampMixin):
    """Customer order (§3.2): date, customer, address, details, status."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NEW','CONFIRMED','IN_PRODUCTION','READY','SHIPPED',"
            "'DELIVERED','CANCELLED')",
            name="status",
        ),
        CheckConstraint("channel IN ('direct','marketplace')", name="channel"),
        Index("ix_orders_status", "status", "order_date"),
        Index("ix_orders_customer", "customer_name"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    order_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    order_date: Mapped[str] = mapped_column(Text, nullable=False)
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="NEW")
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="direct")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.position"
    )


class OrderItem(Base):
    """One line of an order — the «order details»."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("variant IN ('plain','chain')", name="variant"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint("weight_g >= 0", name="weight_non_negative"),
        CheckConstraint("print_hours >= 0", name="hours_non_negative"),
        Index("ix_order_items_order", "order_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    order_id: Mapped[str] = mapped_column(
        Text, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str] = mapped_column(Text, nullable=False, default="plain")
    quantity: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False, default=Decimal(1))
    unit_price: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    weight_g: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    print_hours: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    inventory_item_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")


class ProductionJob(Base, TimestampMixin):
    """Production run (§3.3): consumes filament, yields produced goods."""

    __tablename__ = "production_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNED','IN_PROGRESS','DONE','CANCELLED')", name="status"
        ),
        CheckConstraint("variant IN ('plain','chain')", name="variant"),
        CheckConstraint("channel IN ('direct','marketplace')", name="channel"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("filament_grams >= 0", name="filament_non_negative"),
        CheckConstraint("print_hours >= 0", name="hours_non_negative"),
        CheckConstraint("unit_cost >= 0", name="unit_cost_non_negative"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        Index("ix_production_jobs_status", "status", "created_at"),
        Index("ix_production_jobs_order", "order_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    order_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    order_item_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True
    )
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str] = mapped_column(Text, nullable=False, default="plain")
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="direct")
    quantity: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False, default=Decimal(1))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PLANNED")
    filament_item_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True
    )
    product_item_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True
    )
    filament_grams: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    print_hours: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    unit_price: Mapped[Decimal] = mapped_column(
        ScaledMoneyType, nullable=False, default=Decimal(0)
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

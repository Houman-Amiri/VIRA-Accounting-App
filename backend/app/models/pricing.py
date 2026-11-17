"""Shared pricing preferences; monetary columns are scaled INTEGER Rials."""
from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db_types import ScaledMoneyType
from .base import Base


class PricingSettings(Base):
    __tablename__ = "pricing_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("version_id >= 1", name="version_positive"),
        *(CheckConstraint(f"{field} >= 0", name=f"{field}_non_negative") for field in (
            "filament_per_gram", "electricity_per_kwh", "depreciation_per_hour", "profit_factor",
            "chain_per_unit", "shipment_per_batch", "label_per_unit",
        )),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filament_per_gram: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    electricity_per_kwh: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    depreciation_per_hour: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    profit_factor: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    chain_per_unit: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    shipment_per_batch: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    label_per_unit: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


#: How a custom constant turns into money. Stored in the database verbatim.
CUSTOM_METHODS = ("PER_UNIT", "PER_BATCH", "PERCENT_OF_COST", "PERCENT_OF_PRICE")


class PricingCustomConstant(Base):
    """One owner-defined cost added to the selling price.

    The seven built-in constants mirror the workbook and stay fixed; this table
    lets the owner add his own («هزینهٔ بسته‌بندی»، «کارمزد پست»، …) and choose
    how each one is calculated. It never rewrites a saved price.
    """

    __tablename__ = "pricing_custom_constants"
    __table_args__ = (
        CheckConstraint(
            "method IN ('PER_UNIT','PER_BATCH','PERCENT_OF_COST','PERCENT_OF_PRICE')",
            name="method",
        ),
        CheckConstraint("value >= 0", name="value_non_negative"),
        CheckConstraint("is_active IN (0, 1)", name="is_active_flag"),
        Index("ix_pricing_custom_constants_order", "position", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(ScaledMoneyType, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

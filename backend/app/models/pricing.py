"""Shared pricing preferences; monetary columns are scaled INTEGER Rials."""
from decimal import Decimal

from sqlalchemy import CheckConstraint, Integer, Text
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

"""Pricing amounts travel as exact decimal strings in Toman, never floats."""
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_serializer

Amount = Annotated[Decimal, Field(ge=0, le=Decimal("1000000000000"), decimal_places=4)]


class PricingValues(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    filament_per_gram: Amount = Field(alias="filamentPerGram")
    electricity_per_kwh: Amount = Field(alias="electricityPerKwh")
    depreciation_per_hour: Amount = Field(alias="depreciationPerHour")
    profit_factor: Annotated[Decimal, Field(ge=0, le=1000, decimal_places=4)] = Field(alias="profitFactor")
    chain_per_unit: Amount = Field(alias="chainPerUnit")
    shipment_per_batch: Amount = Field(alias="shipmentPerBatch")
    label_per_unit: Amount = Field(alias="labelPerUnit")

    @field_serializer(
        "filament_per_gram", "electricity_per_kwh", "depreciation_per_hour", "profit_factor",
        "chain_per_unit", "shipment_per_batch", "label_per_unit", when_used="json",
    )
    def serialize_amount(self, value: Decimal) -> str:
        return f"{value:.4f}"


class PricingUpdate(PricingValues):
    version_id: int = Field(ge=1)


class PricingRead(PricingUpdate):
    updated_at: str

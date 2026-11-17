"""Pricing amounts travel as exact decimal strings in Toman, never floats."""
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

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


# ------------------------------------------------- owner-defined constants ---
CustomMethod = Literal["PER_UNIT", "PER_BATCH", "PERCENT_OF_COST", "PERCENT_OF_PRICE"]

#: Percent methods are bounded like the profit factor; money methods like money.
MAX_PERCENT = Decimal("1000")


class PricingCustomConstantCreate(BaseModel):
    """One owner-defined constant: a name, a method and a value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    method: CustomMethod
    value: Amount
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("نام ثابت نمی‌تواند خالی باشد")
        return cleaned

    @model_validator(mode="after")
    def bound_percent(self) -> "PricingCustomConstantCreate":
        if self.method.startswith("PERCENT") and self.value > MAX_PERCENT:
            raise ValueError(f"درصد نمی‌تواند از {MAX_PERCENT} بیشتر باشد")
        return self


class PricingCustomConstantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    method: CustomMethod | None = None
    value: Amount | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("نام ثابت نمی‌تواند خالی باشد")
        return cleaned


class PricingCustomConstantRead(BaseModel):
    id: str
    name: str
    method: CustomMethod
    value: str
    is_active: bool
    position: int
    created_at: str
    updated_at: str

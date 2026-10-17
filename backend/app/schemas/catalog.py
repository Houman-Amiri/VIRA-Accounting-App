"""Shared catalog contracts; identities/operational semantics are immutable."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CatalogCategory = Literal["types", "units"]


def clean_name(value: str) -> str:
    value = " ".join(
        unicodedata.normalize("NFKC", value).replace("ي", "ی").replace("ك", "ک").split()
    )
    if not value or len(value) > 200:
        raise ValueError("نام باید بین یک تا ۲۰۰ نویسه باشد")
    if any(unicodedata.category(c).startswith("C") and c != "\u200c" for c in value):
        raise ValueError("نام دارای نویسهٔ کنترلی نامعتبر است")
    return value


class CatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    _clean_name = field_validator("name")(clean_name)


class CatalogState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: int = Field(ge=1)
    is_active: bool


class CatalogRead(BaseModel):
    id: str
    name: str
    is_active: bool
    version_id: int
    required_unit: str | None = None
    production_role: str = "NONE"


class CatalogDeletion(BaseModel):
    action: Literal["deleted", "deactivated"]
    reason: str
    version_id: int | None = None

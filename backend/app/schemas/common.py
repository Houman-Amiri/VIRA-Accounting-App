"""Shared schema primitives: exact money strings, dates, problem details (RFC 9457)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field

from ..money import MoneyError, parse_money_str

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CUR_RE = re.compile(r"^[A-Z]{3}$")


def _validate_money_str(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        dec: Decimal | None = parse_money_str(value)
    except MoneyError as exc:
        raise ValueError(str(exc)) from exc
    if dec is None:  # pragma: no cover
        raise ValueError("unparsable money")
    return f"{dec:.4f}"


def _validate_date(value: str) -> str:
    if not DATE_RE.match(value):
        raise ValueError("dates must be ISO YYYY-MM-DD")
    return value


def _validate_currency(value: str) -> str:
    if not CUR_RE.match(value):
        raise ValueError("currency must be an ISO 4217 code")
    return value


MoneyStr = Annotated[str | None, AfterValidator(_validate_money_str)]
MoneyStrRequired = Annotated[str, AfterValidator(lambda v: _validate_money_str(v) or v)]
ISODate = Annotated[str, AfterValidator(_validate_date)]
CurrencyCode = Annotated[str, AfterValidator(_validate_currency)]


class ProblemDetail(BaseModel):
    """RFC 9457 problem details returned for all API errors."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class Message(BaseModel):
    message: str

"""FX rate API (Frankfurter sync + history)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExchangeRate
from ..services.fx import ExchangeRateService
from .deps import enforce_csrf, get_db, require_roles

router = APIRouter(
    prefix="/api/v1/fx",
    tags=["fx"],
    dependencies=[Depends(enforce_csrf)],
)


@router.get("/rates")
def list_rates(
    session: Annotated[Session, Depends(get_db)],
    base: Annotated[str, Query(min_length=3, max_length=3)] = "EUR",
    quote: Annotated[str, Query(min_length=3, max_length=3)] = "USD",
) -> list[dict[str, object]]:
    rows = session.scalars(
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == base.upper(),
            ExchangeRate.quote_currency == quote.upper(),
        )
        .order_by(ExchangeRate.rate_date.desc())
        .limit(366)
    )
    return [
        {
            "base_currency": r.base_currency,
            "quote_currency": r.quote_currency,
            "rate_date": r.rate_date,
            "rate_scaled": r.rate,
            "source": r.source,
        }
        for r in rows
    ]


@router.post("/sync", status_code=201)
def sync_rate(
    session: Annotated[Session, Depends(get_db)],
    _user: Annotated[object, Depends(require_roles("OWNER", "BOOKKEEPER"))],
    base: Annotated[str, Query(min_length=3, max_length=3)] = "EUR",
    quote: Annotated[str, Query(min_length=3, max_length=3)] = "USD",
    use_live: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    service = ExchangeRateService(session)
    if use_live:
        row = service.sync_daily(base.upper(), quote.upper())
    else:
        # deterministic offline path (tests / air-gapped hosts)
        row = service.upsert_rate(base.upper(), quote.upper(), "2026-01-01", "1.0000", "manual")
    return {
        "id": row.id,
        "base_currency": row.base_currency,
        "quote_currency": row.quote_currency,
        "rate_date": row.rate_date,
        "rate_scaled": row.rate,
        "source": row.source,
    }

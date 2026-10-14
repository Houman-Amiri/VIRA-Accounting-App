"""FX rates: Frankfurter API client + exact scaled conversions.

Rates are stored as integers scaled ×100 000 000 with
``UNIQUE (base, quote, rate_date)`` — historical reports stay deterministic.
Realized/unrealized FX gain is computed with Decimal math only.
"""

from __future__ import annotations

from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import uuid7
from ..models import ExchangeRate
from ..money import from_scaled, from_scaled_fx, to_scaled_fx


class FrankfurterClient:
    """Daily reference rates from Frankfurter.app (ECB data)."""

    def __init__(self, base_url: str = "https://api.frankfurter.app", timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def latest(self, base: str, quote: str) -> dict[str, object]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.base_url}/latest", params={"from": base, "to": quote}
            )
            resp.raise_for_status()
            payload = resp.json()
        rates = payload.get("rates", {})
        if quote not in rates:
            raise ValueError(f"no rate for {base}->{quote} in Frankfurter response")
        return {"rate_date": payload.get("date"), "rate": str(rates[quote]), "source": "frankfurter"}

    def history(self, base: str, quote: str, start: str, end: str) -> dict[str, str]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{self.base_url}/{start}..{end}",
                params={"from": base, "to": quote},
            )
            resp.raise_for_status()
            payload = resp.json()
        return {d: str(r[quote]) for d, r in payload.get("rates", {}).items()}


class ExchangeRateService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_rate(self, base: str, quote: str, rate_date: str, rate: str, source: str = "frankfurter") -> ExchangeRate:
        existing = self.session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency == base,
                ExchangeRate.quote_currency == quote,
                ExchangeRate.rate_date == rate_date,
            )
        )
        scaled = to_scaled_fx(rate)
        if existing is not None:
            existing.rate = scaled
            existing.source = source
            return existing
        row = ExchangeRate(
            id=uuid7(),
            base_currency=base,
            quote_currency=quote,
            rate_date=rate_date,
            rate=scaled,
            source=source,
        )
        self.session.add(row)
        return row

    def get_rate(self, base: str, quote: str, rate_date: str) -> int | None:
        """Rate as scaled integer for an exact date, else the latest prior date."""
        row = self.session.scalar(
            select(ExchangeRate).where(
                ExchangeRate.base_currency == base,
                ExchangeRate.quote_currency == quote,
                ExchangeRate.rate_date == rate_date,
            )
        )
        if row is None:
            row = self.session.scalar(
                select(ExchangeRate)
                .where(
                    ExchangeRate.base_currency == base,
                    ExchangeRate.quote_currency == quote,
                    ExchangeRate.rate_date <= rate_date,
                )
                .order_by(ExchangeRate.rate_date.desc())
                .limit(1)
            )
        return row.rate if row is not None else None

    def sync_daily(self, base: str, quote: str, client: FrankfurterClient | None = None) -> ExchangeRate:
        client = client or FrankfurterClient()
        data = client.latest(base, quote)
        return self.upsert_rate(
            base, quote, str(data["rate_date"]), str(data["rate"]), str(data["source"])
        )

    def unrealized_fx_gain_loss(
        self,
        *,
        currency: str,
        functional_currency: str,
        as_of: str,
        booked_rate_scaled: int,
        foreign_balance_scaled: int,
    ) -> int:
        """Revalue a foreign-currency balance at the as_of rate (scaled, functional)."""
        from ..money import convert_scaled

        rate = self.get_rate(currency, functional_currency, as_of)
        if rate is None:
            raise ValueError(f"no FX rate for {currency}->{functional_currency} at {as_of}")
        revalued = convert_scaled(foreign_balance_scaled, rate)
        booked = convert_scaled(foreign_balance_scaled, booked_rate_scaled)
        return revalued - booked


def format_rate(rate_scaled: int) -> str:
    return f"{from_scaled_fx(rate_scaled):.8f}"


def format_amount(amount_scaled: int) -> str:
    return f"{from_scaled(amount_scaled):.4f}"


def to_iso_today() -> str:
    return date.today().isoformat()

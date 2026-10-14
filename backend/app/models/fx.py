"""Multi-currency FX history (rates scaled ×100 000 000)."""

from __future__ import annotations

from sqlalchemy import Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency", "quote_currency", "rate_date", name="rate_pair_date"
        ),
        Index("ix_exchange_rates_date", "rate_date"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    base_currency: Mapped[str] = mapped_column(Text, nullable=False)
    quote_currency: Mapped[str] = mapped_column(Text, nullable=False)
    rate_date: Mapped[str] = mapped_column(Text, nullable=False)  # YYYY-MM-DD
    rate: Mapped[int] = mapped_column(Integer, nullable=False)  # scaled 1e8
    source: Mapped[str] = mapped_column(Text, nullable=False, default="frankfurter")

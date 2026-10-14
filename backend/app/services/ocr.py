"""Receipt OCR & structured extraction.

Local-first: PaddleOCR/Tesseract extract raw text; optional Instructor +
LiteLLM parse messy receipt text into strict Pydantic models.  External vision
LLMs require an explicit opt-in (privacy-first).  All engines are optional
imports behind a small protocol.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

from ..money import MoneyError, parse_money_str


class ReceiptLineItem(BaseModel):
    description: str
    quantity: Decimal = Decimal(1)
    amount: str = "0.0000"


class ReceiptData(BaseModel):
    merchant: str | None = None
    date: str | None = None
    subtotal: str | None = None
    tax: str | None = None
    total: str | None = None
    currency: str = "IRR"
    line_items: list[ReceiptLineItem] = Field(default_factory=list)

    def validated(self) -> ReceiptData:
        for name in ("subtotal", "tax", "total"):
            value = getattr(self, name)
            if value is not None:
                try:
                    parse_money_str(value)
                except MoneyError as exc:
                    raise ValueError(f"invalid {name}: {value}") from exc
        if self.date:
            date.fromisoformat(self.date)  # raises on bad format
        return self


class OCREngine(Protocol):
    def extract_text(self, data: bytes) -> str: ...


class TesseractOCREngine:
    def extract_text(self, data: bytes) -> str:
        try:
            import io

            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pytesseract/Pillow not installed") from exc
        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img, lang="fas+eng")


class NoOpOCREngine:
    def extract_text(self, data: bytes) -> str:
        return ""


def default_engine() -> OCREngine:
    try:
        return TesseractOCREngine()
    except Exception:
        return NoOpOCREngine()


def parse_receipt_text(text: str) -> ReceiptData:
    """Lightweight deterministic extraction (regex/lines) — the local path.

    The LLM path (Instructor + LiteLLM) is an optional accelerator; this
    function is the always-available baseline and keeps behavior testable.
    """
    import re

    merchant = None
    total = None
    date_value = None
    for line in text.splitlines():
        stripped = line.strip()
        if merchant is None and stripped and not stripped[0].isdigit():
            merchant = stripped
        m = re.search(r"(?:total|جمع|مبلغ کل)\D*([\d,\.]+)", stripped, re.I)
        if m and total is None:
            total = m.group(1).replace(",", "")
        d = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", stripped)
        if d and date_value is None:
            date_value = d.group(1).replace("/", "-")
    return ReceiptData(merchant=merchant, total=total, date=date_value).validated()


def parse_receipt_with_llm(text: str, *, opt_in: bool = False) -> ReceiptData:  # pragma: no cover
    """Optional Instructor + LiteLLM structured extraction (explicit opt-in)."""
    if not opt_in:
        raise RuntimeError("external LLM extraction requires explicit opt-in")
    try:
        import instructor  # type: ignore[import-untyped]
        import litellm  # type: ignore[import-untyped]
    except Exception as exc:
        raise RuntimeError("instructor/litellm not installed") from exc
    client = instructor.from_litellm(litellm.completion)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=ReceiptData,
        messages=[{"role": "user", "content": f"Extract receipt fields:\n{text}"}],
    )
    return resp.validated()

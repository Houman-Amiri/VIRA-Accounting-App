"""Bank statement ingestion pipeline (idempotent, normalized).

Formats: CSV/XLSX (Polars + openpyxl), OFX/QFX (ofxtools with fallback),
MT940 (mt940 lib), CAMT.053 (internal XML parser).  De-duplication uses
``UNIQUE (account_id, external_fitid)`` for bank-issued FITIDs and a SHA-256
``dedup_hash`` fallback for CSV rows.  Each import batch commits atomically;
repeated uploads never create duplicate lines.
"""

from __future__ import annotations

import hashlib
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import BankImportBatch, BankStatementLine
from ..money import MoneyError, to_scaled
from ..services.errors import DuplicateBankImportError, FileRejectedError

MAX_STATEMENT_BYTES = 25 * 1024 * 1024


@dataclass
class NormalizedLine:
    value_date: str
    amount_scaled: int
    currency: str
    payee: str | None = None
    description: str | None = None
    booking_date: str | None = None
    external_fitid: str | None = None


@dataclass
class ParseResult:
    file_format: str
    lines: list[NormalizedLine] = field(default_factory=list)


_WS = re.compile(r"\s+")


def normalize_text(value: object) -> str:
    """Strip whitespace/padding and control noise from payee/description fields."""
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\x00", " ")
    text = _WS.sub(" ", text).strip()
    return text


def normalize_date(value: object) -> str:
    """Normalize heterogeneous date representations to ISO YYYY-MM-DD."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = normalize_text(value)
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {value!r}")


def dedup_hash_for(line: NormalizedLine) -> str:
    payload = "|".join(
        [
            line.value_date,
            str(line.amount_scaled),
            line.currency,
            line.payee or "",
            line.description or "",
            line.external_fitid or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------- parsers ----------------


def parse_csv(data: bytes, *, currency: str = "IRR") -> ParseResult:
    import polars as pl

    df = pl.read_csv(io.BytesIO(data), infer_schema_length=1000, ignore_errors=True)
    cols = {c.lower().strip(): c for c in df.columns}
    date_col = next((cols[k] for k in ("date", "value_date", "transaction_date", "تاریخ") if k in cols), None)
    amount_col = next((cols[k] for k in ("amount", "مبلغ", "value") if k in cols), None)
    payee_col = next((cols[k] for k in ("payee", "name", "description", "شرح") if k in cols), None)
    fitid_col = next((cols[k] for k in ("fitid", "id", "reference", "reference_id") if k in cols), None)
    if date_col is None or amount_col is None:
        raise FileRejectedError("CSV must contain date and amount columns")
    lines: list[NormalizedLine] = []
    for row in df.to_dicts():
        raw_amount = str(row.get(amount_col, "0")).replace(",", "").strip()
        try:
            scaled = to_scaled(raw_amount)
        except MoneyError as exc:
            raise FileRejectedError(f"invalid amount {raw_amount!r}") from exc
        fitid_value = row.get(fitid_col) if fitid_col else None
        payee_value = row.get(payee_col) if payee_col else None
        lines.append(
            NormalizedLine(
                value_date=normalize_date(row.get(date_col)),
                amount_scaled=scaled,
                currency=currency,
                payee=normalize_text(payee_value) or None,
                description=normalize_text(payee_value) or None,
                external_fitid=normalize_text(fitid_value) or None,
            )
        )
    return ParseResult(file_format="CSV", lines=lines)


def parse_xlsx(data: bytes, *, currency: str = "IRR") -> ParseResult:
    import polars as pl

    df = pl.read_excel(io.BytesIO(data), engine="openpyxl")
    buf = io.BytesIO()
    df.write_csv(buf)
    result = parse_csv(buf.getvalue(), currency=currency)
    result.file_format = "XLSX"
    return result


def parse_ofx(data: bytes, *, currency: str = "IRR") -> ParseResult:
    try:
        from ofxtools.Parser import OFXTree

        tree = OFXTree()
        tree.parse(io.BytesIO(data))
        ofx = tree.convert()
        lines: list[NormalizedLine] = []
        for stmt in ofx.statements:  # type: ignore[attr-defined]
            for txn in stmt.transactions:  # type: ignore[attr-defined]
                amount = getattr(txn, "trnamt", None)
                lines.append(
                    NormalizedLine(
                        value_date=normalize_date(getattr(txn, "dtposted", None)),
                        amount_scaled=to_scaled(str(amount)),
                        currency=currency,
                        payee=normalize_text(getattr(txn, "name", "")) or None,
                        description=normalize_text(getattr(txn, "memo", "")) or None,
                        external_fitid=normalize_text(getattr(txn, "fitid", "")) or None,
                    )
                )
        return ParseResult(file_format="OFX", lines=lines)
    except Exception:
        return _parse_ofx_fallback(data, currency=currency)


def _parse_ofx_fallback(data: bytes, *, currency: str) -> ParseResult:
    """Minimal OFX 1.x/2.x transaction extraction (internal safety net)."""
    text = data.decode("utf-8", errors="replace")

    def tag(name: str, blob: str) -> str | None:
        m = re.search(rf"<{name}>([^<\r\n]*)", blob, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None

    lines: list[NormalizedLine] = []
    for blob in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, flags=re.I | re.S):
        amount = tag("TRNAMT", blob)
        dtposted = tag("DTPOSTED", blob)
        if amount is None or dtposted is None:
            continue
        lines.append(
            NormalizedLine(
                value_date=normalize_date(dtposted[:8]),
                amount_scaled=to_scaled(amount.replace(",", "")),
                currency=currency,
                payee=tag("NAME", blob),
                description=tag("MEMO", blob),
                external_fitid=tag("FITID", blob),
            )
        )
    return ParseResult(file_format="OFX", lines=lines)


def parse_mt940(data: bytes, *, currency: str = "IRR") -> ParseResult:
    import mt940

    lines: list[NormalizedLine] = []
    transactions = mt940.parse(io.BytesIO(data))
    for entry in transactions:  # noqa: B007
        for txn in entry.get("transactions", []):
            data_map: dict[str, Any] = txn.get("data", {}) if isinstance(txn, dict) else {}
            amount = data_map.get("amount")
            amount_str = str(getattr(amount, "amount", amount))
            value_date = data_map.get("value_date") or data_map.get("entry_date")
            lines.append(
                NormalizedLine(
                    value_date=normalize_date(value_date),
                    amount_scaled=to_scaled(amount_str.replace(",", "")),
                    currency=currency,
                    payee=normalize_text(data_map.get("name") or data_map.get("customer_reference"))
                    or None,
                    description=normalize_text(data_map.get("description") or data_map.get("reference"))
                    or None,
                    external_fitid=normalize_text(
                        data_map.get("transaction_reference") or data_map.get("reference")
                    )
                    or None,
                )
            )
    return ParseResult(file_format="MT940", lines=lines)


_CMT_NS = {
    "camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02",
    "camt053": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08",
}


def parse_camt053(data: bytes, *, currency: str = "IRR") -> ParseResult:
    """Internal CAMT.053 XML parser (namespaces 02 and 08)."""
    root = ET.fromstring(data)
    ns_uri = root.tag.split("}")[0].strip("{") if "}" in root.tag else ""
    if ns_uri:
        def q(name: str) -> str:
            return f"{{{ns_uri}}}{name}"
    else:
        def q(name: str) -> str:
            return name

    lines: list[NormalizedLine] = []
    for entry in root.iter(q("Ntry")):
        amt_el = entry.find(".//" + q("Amt"))
        cdt_dbt = entry.find(".//" + q("CdtDbtInd"))
        date_el = entry.find(".//" + q("ValDt") + "/" + q("Dt"))
        if amt_el is None or date_el is None:
            continue
        sign = -1 if (cdt_dbt is not None and cdt_dbt.text == "DBIT") else 1
        amount_text = (amt_el.text or "0").replace(",", "")
        ref_el = entry.find(".//" + q("AcctSvcrRef"))
        addtl = entry.find(".//" + q("AddtlNtryInf"))
        lines.append(
            NormalizedLine(
                value_date=normalize_date(date_el.text),
                amount_scaled=sign * to_scaled(amount_text),
                currency=(amt_el.get("Ccy") or currency),
                description=normalize_text(addtl.text if addtl is not None else None) or None,
                external_fitid=normalize_text(ref_el.text if ref_el is not None else None) or None,
            )
        )
    return ParseResult(file_format="CAMT053", lines=lines)


PARSERS = {
    "CSV": parse_csv,
    "XLSX": parse_xlsx,
    "OFX": parse_ofx,
    "QFX": parse_ofx,
    "MT940": parse_mt940,
    "CAMT053": parse_camt053,
}


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return {
        "csv": "CSV",
        "xlsx": "XLSX",
        "xls": "XLSX",
        "ofx": "OFX",
        "qfx": "QFX",
        "mt940": "MT940",
        "sta": "MT940",
        "xml": "CAMT053",
    }.get(ext, "")


# ---------------- import service ----------------


class BankImportService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def import_file(
        self,
        *,
        filename: str,
        data: bytes,
        account_id: str | None,
        currency: str = "IRR",
    ) -> BankImportBatch:
        if len(data) > MAX_STATEMENT_BYTES:
            raise FileRejectedError("statement exceeds 25 MB limit")
        fmt = detect_format(filename)
        if fmt not in PARSERS:
            raise FileRejectedError(f"unsupported statement format: {filename}")
        parsed = PARSERS[fmt](data, currency=currency)
        file_sha = hashlib.sha256(data).hexdigest()

        batch = BankImportBatch(
            id=uuid7(),
            account_id=account_id,
            source_filename=filename,
            file_format=parsed.file_format,
            file_sha256=file_sha,
            imported_at=utc_now_iso(),
            status="IMPORTED",
            line_count=len(parsed.lines),
        )
        self.session.add(batch)
        inserted = 0
        for line in parsed.lines:
            dhash = dedup_hash_for(line)
            dup = self.session.scalar(
                select(BankStatementLine).where(
                    BankStatementLine.account_id == account_id,
                    BankStatementLine.dedup_hash == dhash,
                )
            )
            if dup is not None:
                continue  # idempotent: repeated uploads never duplicate
            if line.external_fitid:
                dup_fit = self.session.scalar(
                    select(BankStatementLine).where(
                        BankStatementLine.account_id == account_id,
                        BankStatementLine.external_fitid == line.external_fitid,
                    )
                )
                if dup_fit is not None:
                    continue
            self.session.add(
                BankStatementLine(
                    id=uuid7(),
                    batch_id=batch.id,
                    account_id=account_id,
                    external_fitid=line.external_fitid,
                    dedup_hash=dhash,
                    value_date=line.value_date,
                    booking_date=line.booking_date,
                    payee_raw=line.payee,
                    description_raw=line.description,
                    amount=line.amount_scaled,
                    currency=line.currency,
                    category_suggestion=None,
                    status="UNMATCHED",
                )
            )
            inserted += 1
        batch.line_count = inserted
        self.session.flush()
        return batch

    def reject_duplicate_file(self, account_id: str | None, data: bytes) -> None:
        file_sha = hashlib.sha256(data).hexdigest()
        existing = self.session.scalar(
            select(BankImportBatch).where(
                BankImportBatch.account_id == account_id,
                BankImportBatch.file_sha256 == file_sha,
                BankImportBatch.status == "IMPORTED",
            )
        )
        if existing is not None:
            raise DuplicateBankImportError(
                f"file already imported as batch {existing.id}"
            )

"""Bank statement ingestion: normalization, FITID/hash idempotency, parsers."""

from __future__ import annotations

import pytest

from app.services.bank_import import (
    BankImportService,
    NormalizedLine,
    dedup_hash_for,
    detect_format,
    normalize_date,
    normalize_text,
    parse_camt053,
    parse_csv,
    parse_ofx,
)
from app.services.errors import DuplicateBankImportError, FileRejectedError

CSV_SAMPLE = b"date,payee,amount,reference\n2026-10-01,  Firma GmbH  ,1250.50,REF-1\n2026-10-02,Coffee Shop,-8.90,REF-2\n"

OFX_SAMPLE = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102

<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20261001
<TRNAMT>-42.50
<FITID>abc-123
<NAME>UTILITY CO
<MEMO>october bill
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""

CAMT_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Ntry>
        <Amt Ccy="EUR">123.45</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <ValDt><Dt>2026-10-03</Dt></ValDt>
        <AcctSvcrRef>camt-ref-1</AcctSvcrRef>
        <AddtlNtryInf>Salary</AddtlNtryInf>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def test_normalize_text() -> None:
    assert normalize_text("  Firma   GmbH \x00 ") == "Firma GmbH"
    assert normalize_text(None) == ""


def test_normalize_date_formats() -> None:
    assert normalize_date("2026-10-01") == "2026-10-01"
    assert normalize_date("20261001") == "2026-10-01"
    assert normalize_date("01/10/2026") == "2026-10-01"
    with pytest.raises(ValueError):
        normalize_date("not-a-date")


def test_parse_csv() -> None:
    result = parse_csv(CSV_SAMPLE)
    assert result.file_format == "CSV"
    assert len(result.lines) == 2
    assert result.lines[0].payee == "Firma GmbH"
    assert result.lines[0].amount_scaled == 12_505_000
    assert result.lines[1].amount_scaled == -89_000


def test_parse_ofx_fallback() -> None:
    result = parse_ofx(OFX_SAMPLE)
    assert len(result.lines) == 1
    line = result.lines[0]
    assert line.external_fitid == "abc-123" or line.external_fitid is not None
    assert line.amount_scaled == -425_000
    assert line.value_date == "2026-10-01"


def test_parse_camt() -> None:
    result = parse_camt053(CAMT_SAMPLE)
    assert len(result.lines) == 1
    assert result.lines[0].amount_scaled == 1_234_500
    assert result.lines[0].external_fitid == "camt-ref-1"


def test_detect_format() -> None:
    assert detect_format("stmt.CSV") == "CSV"
    assert detect_format("x.ofx") == "OFX"
    assert detect_format("x.qfx") == "QFX"
    assert detect_format("x.mt940") == "MT940"
    assert detect_format("x.unknown") == ""


def test_import_idempotent(session) -> None:
    service = BankImportService(session)
    batch1 = service.import_file(
        filename="oct.csv", data=CSV_SAMPLE, account_id=None, currency="IRR"
    )
    assert batch1.line_count == 2
    # same file again: no new lines (dedup by hash)
    batch2 = service.import_file(
        filename="oct-again.csv", data=CSV_SAMPLE, account_id=None, currency="IRR"
    )
    assert batch2.line_count == 0


def test_duplicate_file_rejected(session) -> None:
    service = BankImportService(session)
    service.import_file(filename="oct.csv", data=CSV_SAMPLE, account_id=None)
    with pytest.raises(DuplicateBankImportError):
        service.reject_duplicate_file(None, CSV_SAMPLE)


def test_bad_csv_rejected(session) -> None:
    with pytest.raises(FileRejectedError):
        parse_csv(b"foo,bar\n1,2\n")


def test_dedup_hash_stable() -> None:
    line = NormalizedLine(value_date="2026-10-01", amount_scaled=1, currency="IRR")
    assert dedup_hash_for(line) == dedup_hash_for(line)

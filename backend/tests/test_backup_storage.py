"""Backups (online API + restore verification), storage, OCR, FX, audit, scheduler."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog
from app.schemas.ledger import AccountCreate, JournalEntryCreate, SplitCreate
from app.services.backup import create_backup, restore_verified
from app.services.errors import FileTooLarge, UnsupportedMediaType
from app.services.fx import ExchangeRateService
from app.services.ledger import LedgerService
from app.services.ocr import parse_receipt_text
from app.services.scheduler import RecurringEntryService
from app.services.storage import save_receipt, sniff_kind, strip_image_metadata

# ---------------- backups ----------------


def test_online_backup_and_verify(database, tmp_path: Path) -> None:
    with database.session() as session:
        service = LedgerService(session)
        cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
        eq = service.create_account(AccountCreate(code="3010", name="سرمایه", account_type="EQUITY"))
        service.create_draft(
            JournalEntryCreate(
                transaction_date="2026-10-14",
                description="seed for backup",
                splits=[
                    SplitCreate(account_id=cash.id, debit="10"),
                    SplitCreate(account_id=eq.id, credit="10"),
                ],
            ),
            post=True,
        )
    target = tmp_path / "backups" / "snap.sqlite3"
    result = create_backup(database.settings.sqlite_database_path, target)
    assert result.ok
    assert result.integrity_check == "ok"
    assert result.total_debits == result.total_credits == 100_000

    drill = restore_verified(database.settings.sqlite_database_path, target)
    assert drill.integrity_check == "ok"
    assert drill.ok


# ---------------- storage ----------------


def test_sniff_and_strip() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"rest"
    assert sniff_kind(png) == "png"
    assert sniff_kind(b"%PDF-1.4") == "pdf"
    assert sniff_kind(b"junk") is None
    assert strip_image_metadata(png, "png") == png  # Pillow failure keeps bytes


def test_content_addressed_storage(tmp_path: Path) -> None:
    data = b"%PDF-1.4 fake receipt"
    meta1 = save_receipt(data, "r1.pdf", tmp_path)
    meta2 = save_receipt(data, "r2.pdf", tmp_path)
    assert meta1["sha256"] == meta2["sha256"]  # dedup by content
    assert (tmp_path / str(meta1["storage_path"])).exists()

    with pytest.raises(UnsupportedMediaType):
        save_receipt(b"not a receipt", "x.txt", tmp_path)
    with pytest.raises(FileTooLarge):
        save_receipt(b"%PDF-" + b"0" * (11 * 1024 * 1024), "big.pdf", tmp_path)


# ---------------- ocr ----------------


def test_parse_receipt_text() -> None:
    text = "فروشگاه نمونه\n2026-10-14\nمبلغ کل 125,000\n"
    data = parse_receipt_text(text)
    assert data.merchant == "فروشگاه نمونه"
    assert data.date == "2026-10-14"
    assert data.total == "125000"


# ---------------- fx ----------------


def test_exchange_rate_service(session) -> None:
    service = ExchangeRateService(session)
    service.upsert_rate("EUR", "IRR", "2026-10-01", "72000.5", "test")
    rate = service.get_rate("EUR", "IRR", "2026-10-14")
    assert rate == 7_200_050_000_000  # 72000.5 × 1e8
    # date-before-nothing -> latest prior
    assert service.get_rate("EUR", "IRR", "2026-09-01") is None
    gain = service.unrealized_fx_gain_loss(
        currency="EUR",
        functional_currency="IRR",
        as_of="2026-10-14",
        booked_rate_scaled=7_200_000_000_000,
        foreign_balance_scaled=100_000,  # 10.0000 EUR
    )
    # rate delta 0.5 IRR/EUR × 10 EUR = 5 IRR = 50 000 scaled
    assert gain == 50_000


# ---------------- audit ----------------


def test_audit_trail_captured_and_immutable(session) -> None:
    from sqlalchemy import text as sql_text

    service = LedgerService(session)
    service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
    session.flush()
    logs = list(session.scalars(select(AuditLog)))
    assert any(row.action == "INSERT" and row.table_name == "accounts" for row in logs)

    log_row = logs[0]
    log_row.action = "DELETE"
    with pytest.raises(IntegrityError):
        session.flush()  # trigger rejects UPDATE of audit_logs
    session.rollback()

    # raw SQL path is rejected by the trigger as well
    with pytest.raises(IntegrityError):
        session.execute(
            sql_text("UPDATE audit_logs SET action='DELETE' WHERE id=:id"),
            {"id": log_row.id},
        )
        session.flush()
    session.rollback()


# ---------------- scheduler ----------------


def test_recurring_entries_posted(session) -> None:
    service = LedgerService(session)
    cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
    exp = service.create_account(AccountCreate(code="5040", name="اجاره", account_type="EXPENSE"))
    recurring = RecurringEntryService(session)
    row = recurring.create(
        name="اجاره ماهانه",
        cron_expr="0 9 1 * *",
        template={
            "description": "اجاره ماهانه",
            "splits": [
                {"account_id": exp.id, "debit": "5000000"},
                {"account_id": cash.id, "credit": "5000000"},
            ],
        },
    )
    row.next_run_at = "2020-01-01T00:00:00+00:00"  # force due
    session.flush()
    executed = recurring.run_due_jobs()
    assert len(executed) == 1
    entry = service.get_entry(executed[0])
    assert entry.status == "POSTED"
    assert "اجاره" in entry.description
    # not due again immediately
    assert recurring.run_due_jobs() == []


# ---------------- encrypted backup bundles (Phase 4 §10) ----------------


def _seed_balanced(database) -> None:
    with database.session() as session:
        service = LedgerService(session)
        cash = service.create_account(AccountCreate(code="1010", name="صندوق", account_type="ASSET"))
        eq = service.create_account(AccountCreate(code="3010", name="سرمایه", account_type="EQUITY"))
        service.create_draft(
            JournalEntryCreate(
                transaction_date="2026-10-14",
                description="bundle seed",
                splits=[
                    SplitCreate(account_id=cash.id, debit="42.0001"),
                    SplitCreate(account_id=eq.id, credit="42.0001"),
                ],
            ),
            post=True,
        )


def test_encrypted_bundle_roundtrip(database, tmp_path: Path) -> None:
    from app.services.backup import create_backup_bundle, restore_bundle

    _seed_balanced(database)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "r1.pdf").write_bytes(b"%PDF-1.4 fake")

    out = tmp_path / "bundle"
    result = create_backup_bundle(
        database.settings.sqlite_database_path,
        out,
        receipts_dir=receipts,
        passphrase="correct-horse-battery",
        version_label="0.1.0",
    )
    assert result.encrypted is True
    assert result.receipts_copied == 1
    assert result.snapshot_path.endswith(".enc")
    assert "manifest.json" in result.files

    # ciphertext is not a SQLite file
    head = Path(result.snapshot_path).read_bytes()[:16]
    assert not head.startswith(b"SQLite format 3")

    drill = restore_bundle(out, passphrase="correct-horse-battery")
    assert drill.ok
    assert drill.integrity_check == "ok"
    assert drill.migration_version is not None
    assert drill.total_debits == drill.total_credits == 420_001

    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        restore_bundle(out, passphrase="wrong-password")


def test_plain_bundle_and_migration_version(database, tmp_path: Path) -> None:
    from app.services.backup import create_backup_bundle, restore_bundle

    _seed_balanced(database)
    out = tmp_path / "bundle-plain"
    result = create_backup_bundle(
        database.settings.sqlite_database_path, out, version_label="0.1.0"
    )
    assert result.encrypted is False
    drill = restore_bundle(out)
    assert drill.ok
    assert drill.migration_version == "0003_security"

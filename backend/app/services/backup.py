"""SQLite online backups + restore verification + optional encryption.

Backups use ``sqlite3.Connection.backup()`` (never a naive file copy that
ignores WAL state).  Restore verification restores to a temporary path and
runs ``PRAGMA integrity_check``, ``PRAGMA foreign_key_check``, the Alembic
migration version check and the ledger debit/credit equality check before a
backup is considered valid.

Phase 4 §10: snapshots can be encrypted (Fernet, key derived from a passphrase
via PBKDF2-HMAC-SHA256) and bundled with the receipt storage plus a manifest.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 480_000
_ENCRYPTED_SUFFIX = ".enc"


@dataclass
class BackupResult:
    path: str
    size_bytes: int
    integrity_check: str
    foreign_key_violations: int
    total_debits: int
    total_credits: int
    ok: bool
    migration_version: str | None = None


@dataclass
class BackupBundleResult:
    manifest_path: str
    snapshot_path: str
    encrypted: bool
    receipts_copied: int
    backup: BackupResult | None = None
    files: list[str] = field(default_factory=list)


def create_backup(db_path: Path | str, backup_path: Path | str) -> BackupResult:
    db_path = Path(db_path)
    backup_path = Path(backup_path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        backup_path.unlink()
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    try:
        with dst:
            src.backup(dst)  # online backup API — consistent snapshot incl. WAL
    finally:
        src.close()
        dst.close()
    return verify_backup(backup_path)


def verify_backup(backup_path: Path | str) -> BackupResult:
    backup_path = Path(backup_path)
    conn = sqlite3.connect(backup_path)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
        migration_version: str | None = None
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            migration_version = str(row[0]) if row else None
        except sqlite3.OperationalError:
            migration_version = None
        try:
            d, c = conn.execute(
                "SELECT COALESCE(SUM(functional_debit),0), "
                "COALESCE(SUM(functional_credit),0) FROM transaction_splits"
            ).fetchone()
        except sqlite3.OperationalError:
            d, c = (0, 0)
        ok = (
            integrity == "ok"
            and len(fk_rows) == 0
            and int(d) == int(c)
            and migration_version is not None
        )
        return BackupResult(
            path=str(backup_path),
            size_bytes=backup_path.stat().st_size,
            integrity_check=integrity,
            foreign_key_violations=len(fk_rows),
            total_debits=int(d),
            total_credits=int(c),
            ok=ok,
            migration_version=migration_version,
        )
    finally:
        conn.close()


def restore_verified(db_path: Path | str, backup_path: Path | str) -> BackupResult:
    """Restore into a temp location and verify — recovery drill."""
    with tempfile.TemporaryDirectory(prefix="vira-restore-") as tmp:
        target = Path(tmp) / "restored.sqlite3"
        target.write_bytes(Path(backup_path).read_bytes())
        result = verify_backup(target)
        log.info("restore verification for %s: ok=%s", backup_path, result.ok)
        return result


def pre_update_backup(db_path: Path | str, backups_dir: Path | str, version: str) -> BackupResult:
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"pre-update-{version}.sqlite3"
    return create_backup(db_path, target)


# ---------------- encryption (Phase 4 §10) ----------------


def derive_key(passphrase: str, *, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a Fernet key from a passphrase (PBKDF2-HMAC-SHA256)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return key, salt


def encrypt_file(src: Path | str, dst: Path | str, *, key: bytes) -> Path:
    from cryptography.fernet import Fernet

    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    token = Fernet(key).encrypt(src.read_bytes())
    dst.write_bytes(token)
    return dst


def decrypt_file(src: Path | str, dst: Path | str, *, key: bytes) -> Path:
    from cryptography.fernet import Fernet

    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(Fernet(key).decrypt(src.read_bytes()))
    return dst


def create_backup_bundle(
    db_path: Path | str,
    out_dir: Path | str,
    *,
    receipts_dir: Path | str | None = None,
    passphrase: str | None = None,
    version_label: str = "unknown",
) -> BackupBundleResult:
    """Snapshot + receipts + manifest; optional Fernet encryption of the DB.

    Layout (plain):   out_dir/vira-backup.sqlite3
    Layout (locked):  out_dir/vira-backup.sqlite3.enc + backup.key.salt (base64)
    Always:           out_dir/manifest.json and out_dir/receipts/ copy.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot = out_dir / "vira-backup.sqlite3"
    create_backup(db_path, snapshot)

    encrypted = passphrase is not None
    key_material: dict[str, str] = {}
    if passphrase is not None:
        key, salt = derive_key(passphrase)
        enc_path = snapshot.with_name(snapshot.name + _ENCRYPTED_SUFFIX)
        encrypt_file(snapshot, enc_path, key=key)
        snapshot.unlink()
        snapshot = enc_path
        key_material = {
            "kdf": "pbkdf2-hmac-sha256",
            "iterations": str(_PBKDF2_ITERATIONS),
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        }

    receipts_copied = 0
    receipts_out = out_dir / "receipts"
    if receipts_dir is not None and Path(receipts_dir).is_dir():
        shutil.copytree(receipts_dir, receipts_out, dirs_exist_ok=True)
        receipts_copied = sum(1 for p in receipts_out.rglob("*") if p.is_file())

    manifest = {
        "format": "vira-backup-bundle/1",
        "version_label": version_label,
        "encrypted": encrypted,
        "snapshot": snapshot.name,
        "receipts_copied": receipts_copied,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "key_material": key_material,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return BackupBundleResult(
        manifest_path=str(manifest_path),
        snapshot_path=str(snapshot),
        encrypted=encrypted,
        receipts_copied=receipts_copied,
        files=sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file()),
    )


def restore_bundle(
    bundle_dir: Path | str,
    *,
    passphrase: str | None = None,
    target: Path | str | None = None,
) -> BackupResult:
    """Decrypt (if needed) + restore + full verification (recovery drill)."""
    bundle_dir = Path(bundle_dir)
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot = bundle_dir / manifest["snapshot"]
    if manifest.get("encrypted"):
        if passphrase is None:
            raise ValueError("bundle is encrypted — passphrase required")
        salt = base64.b64decode(manifest["key_material"]["salt_b64"])
        key, _ = derive_key(passphrase, salt=salt)
        with tempfile.TemporaryDirectory(prefix="vira-restore-") as tmp:
            plain = Path(tmp) / "restored.sqlite3"
            decrypt_file(snapshot, plain, key=key)
            if target is not None:
                shutil.copy2(plain, target)
                return verify_backup(target)
            return verify_backup(plain)
    if target is not None:
        shutil.copy2(snapshot, target)
        return verify_backup(target)
    return verify_backup(snapshot)

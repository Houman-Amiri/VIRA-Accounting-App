"""System & Operations (Phase 6 §8) — sudo-protected status, encrypted backups,
restore verification and the «بررسی به‌روزرسانی» update check (Phase 8 driver)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import Settings
from ..security.session import SessionUser
from ..security.sudo import require_sudo
from ..version import version_info
from .deps import get_db, get_settings, require_roles, require_user

router = APIRouter(
    prefix="/api/v1/system",
    tags=["system"],
    dependencies=[Depends(require_user)],  # discovery/progress are authenticated reads
)


class BackupStatus(BaseModel):
    at: str | None
    path: str | None
    size_bytes: int | None
    ok: bool | None


class SystemStatus(BaseModel):
    version: str
    commit: str
    #: build id of the SPA shell this install ships (index.html «vira-build») —
    #: the UI compares it with the id it actually loaded and warns on mismatch
    spa_build: str = ""
    environment: str
    python_version: str
    sqlite_version: str
    alembic_revision: str | None
    database_path: str
    receipt_dir: str
    data_dir: str
    scheduler_enabled: bool
    scheduler_running: bool
    scheduler_jobs: int
    last_backup: BackupStatus


class BackupCreated(BaseModel):
    dir: str
    manifest: str
    snapshot: str
    encrypted: bool
    receipts_copied: int
    size_bytes: int


class BackupVerifyReport(BaseModel):
    ok: bool
    restored_to: str
    integrity_check: str
    foreign_key_violations: int
    debits_equal_credits: bool | None
    migration_version: str | None


class UpdatePackage(BaseModel):
    url: str
    sha256: str
    size: int
    from_version: str


class UpdateChoiceOut(BaseModel):
    kind: str  # delta | delta_chain | full
    packages: list[UpdatePackage]
    total_bytes: int


class UpdateCheck(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    notes_fa: str | None
    notes_en: str | None = None
    checked: bool
    reason: str | None = None
    min_app_version: str | None = None
    manual_required: bool = False
    choice: UpdateChoiceOut | None = None


class UpdateApproval(BaseModel):
    expected_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    expected_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class UpdateStatusOut(BaseModel):
    target_version: str = ""
    state: str
    total_bytes: int
    downloaded_bytes: int
    verified: bool
    staged_path: str
    log_path: str
    error_fa: str | None = None
    machine_state: str


def _backups_root(settings: Settings) -> Path:
    assert settings.data_dir is not None
    return Path(settings.data_dir) / "backups"


def _last_backup(settings: Settings) -> BackupStatus:
    backup_root = _backups_root(settings)
    if not backup_root.is_dir():
        return BackupStatus(at=None, path=None, size_bytes=None, ok=None)
    bundles = sorted(backup_root.glob("**/manifest.json"))
    if not bundles:
        return BackupStatus(at=None, path=None, size_bytes=None, ok=None)
    manifest = bundles[-1]
    import json

    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        snapshot = manifest.parent / str(data.get("snapshot", "snapshot.sqlite3"))
        size = snapshot.stat().st_size if snapshot.exists() else None
        return BackupStatus(
            at=str(data.get("created_at") or data.get("created")),
            path=str(manifest.parent),
            size_bytes=size,
            ok=True,
        )
    except Exception:  # noqa: BLE001 - status endpoint must never crash
        return BackupStatus(at=None, path=str(manifest.parent), size_bytes=None, ok=False)


def _scheduler_state(request: Request) -> tuple[bool, bool, int]:
    manager = getattr(request.app.state, "scheduler", None)
    if manager is None:
        return (False, False, 0)
    jobs = 0
    try:
        jobs = len(manager.get_jobs())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - status must not crash
        jobs = 0
    return (True, True, jobs)


@router.get("/status", response_model=SystemStatus, dependencies=[Depends(require_sudo)])
def system_status(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SystemStatus:
    import sqlite3
    import sys

    revision = session.execute(
        text("SELECT version_num FROM alembic_version LIMIT 1")
    ).scalar()
    enabled, running, jobs = _scheduler_state(request)
    return SystemStatus(
        version=version_info()["version"],
        commit=version_info()["commit"],
        spa_build=version_info().get("spa_build", ""),
        environment=settings.environment,
        python_version=sys.version.split()[0],
        sqlite_version=sqlite3.sqlite_version,
        alembic_revision=str(revision) if revision else None,
        database_path=str(settings.sqlite_database_path),
        receipt_dir=str(settings.receipt_dir),
        data_dir=str(settings.data_dir),
        scheduler_enabled=enabled or settings.scheduler_enabled,
        scheduler_running=running,
        scheduler_jobs=jobs,
        last_backup=_last_backup(settings),
    )


@router.post("/backup", response_model=BackupCreated)
def create_backup_now(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> BackupCreated:
    """One-click encrypted snapshot (Sudo step-up already verified)."""
    from ..ids import utc_now_iso
    from ..services.backup import create_backup_bundle
    from ..services.security_audit import record_security_event

    assert settings.sqlite_database_path is not None and settings.receipt_dir is not None
    out_dir = _backups_root(settings) / ("bundle-" + utc_now_iso().replace(":", ""))
    passphrase = settings.app_encryption_key or settings.session_secret
    result = create_backup_bundle(
        settings.sqlite_database_path,
        out_dir,
        receipts_dir=settings.receipt_dir,
        passphrase=passphrase,
        version_label=version_info()["version"],
    )
    snapshot = Path(result.snapshot_path)
    record_security_event(
        session,
        "BACKUP_EXPORTED",
        actor_id=user.user_id,
        detail={"kind": "system-backup", "bundle": str(out_dir)},
    )
    return BackupCreated(
        dir=str(out_dir),
        manifest=result.manifest_path,
        snapshot=result.snapshot_path,
        encrypted=result.encrypted,
        receipts_copied=result.receipts_copied,
        size_bytes=snapshot.stat().st_size if snapshot.exists() else 0,
    )


@router.get("/backup/download")
def download_backup(
    path: str,
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> FileResponse:
    """Download a bundle created by /system/backup — path-traversal guarded."""
    from ..services.security_audit import record_security_event

    backup_root = _backups_root(settings).resolve()
    requested = Path(path).resolve()
    if backup_root not in requested.parents and requested != backup_root:
        from ..services.errors import NotFoundError

        raise NotFoundError("پشتیبان یافت نشد")
    target = requested
    if target.is_dir():
        files = sorted(p for p in target.iterdir() if p.is_file())
        if not files:
            from ..services.errors import NotFoundError

            raise NotFoundError("پشتیبان یافت نشد")
        target = files[0]
    record_security_event(
        session,
        "BACKUP_EXPORTED",
        actor_id=user.user_id,
        detail={"kind": "backup-download", "file": target.name},
    )
    return FileResponse(
        target,
        media_type="application/octet-stream",
        filename=target.name,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{target.name}"',
        },
    )


@router.post("/backup/verify", response_model=BackupVerifyReport)
def verify_backup_bundle(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[SessionUser, Depends(require_sudo)],
    path: str,
) -> BackupVerifyReport:
    """Restore-verification drill: restore to a temp location + full checks."""
    from ..services.backup import restore_bundle

    backup_root = _backups_root(settings).resolve()
    requested = Path(path).resolve()
    if backup_root not in requested.parents:
        from ..services.errors import NotFoundError

        raise NotFoundError("پشتیبان یافت نشد")
    passphrase = settings.app_encryption_key or settings.session_secret
    with tempfile.TemporaryDirectory(prefix="vira-verify-") as tmp:
        target = Path(tmp) / "restored.sqlite3"
        result = restore_bundle(requested, passphrase=passphrase, target=target)
        balanced = result.total_debits == result.total_credits
        from ..services.security_audit import record_security_event

        record_security_event(
            session,
            "BACKUP_EXPORTED",
            actor_id=user.user_id,
            detail={"kind": "backup-verify", "bundle": str(requested), "ok": result.ok},
        )
        return BackupVerifyReport(
            ok=result.ok,
            restored_to=str(target),
            integrity_check=result.integrity_check,
            foreign_key_violations=result.foreign_key_violations,
            debits_equal_credits=balanced,
            migration_version=result.migration_version,
        )


@router.get("/check-updates", response_model=UpdateCheck)
def check_updates(
    settings: Annotated[Settings, Depends(get_settings)],
) -> UpdateCheck:
    """«بررسی به‌روزرسانی» — GitHub Releases + latest.json (Phase 8 §3/§4)."""
    from ..services.update import check_for_update

    result = check_for_update(version_info()["version"], settings)
    choice = None
    if result.choice is not None:
        choice = UpdateChoiceOut(
            kind=result.choice.kind,
            packages=[UpdatePackage(**p) for p in result.choice.packages],
            total_bytes=result.choice.total_bytes,
        )
    return UpdateCheck(
        current=result.current,
        latest=result.latest,
        update_available=result.update_available,
        notes_fa=result.notes_fa or None,
        notes_en=result.notes_en or None,
        checked=result.checked,
        reason=result.reason_fa,
        min_app_version=result.min_app_version or None,
        manual_required=result.manual_required,
        choice=choice,
    )


@router.post("/update/download", response_model=UpdateStatusOut, dependencies=[Depends(require_roles("OWNER"))])
def update_download(
    approval: UpdateApproval,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> UpdateStatusOut:
    """Download + verify the selected package(s) into the staging area (§8)."""
    from ..services.errors import DomainError
    from ..services.update import check_for_update, manager

    result = check_for_update(version_info()["version"], settings)
    if not result.update_available or result.choice is None:
        raise DomainError("به‌روزرسانی موجود نیست")
    if result.manual_required:
        # No delta base for this install (e.g. an unstamped «0.0.0-unknown»
        # build): the full installer must be run by hand, never staged.
        raise DomainError(result.reason_fa or "این به‌روزرسانی نیاز به نصب دستی دارد.")
    if (result.latest != approval.expected_version or result.choice.kind != "delta"
            or len(result.choice.packages) != 1
            or result.choice.packages[0]["sha256"].lower() != approval.expected_sha256.lower()):
        raise DomainError("نسخه یا بسته از زمان تأیید شما تغییر کرده است؛ دوباره بررسی و تأیید کنید.")
    initial = manager.prepare_download(result, settings)
    background_tasks.add_task(manager.finish_download, result)
    return UpdateStatusOut(**initial)


@router.get("/update/status", response_model=UpdateStatusOut)
def update_status(settings: Annotated[Settings, Depends(get_settings)]) -> UpdateStatusOut:
    from ..services.update import read_update_status

    return UpdateStatusOut(**read_update_status(settings))


@router.post("/update/apply", response_model=UpdateStatusOut, dependencies=[Depends(require_roles("OWNER"))])
def update_apply(
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[SessionUser, Depends(require_sudo)],
) -> UpdateStatusOut:
    """Pre-update backup (§7) then launch the transactional updater (§6)."""
    from ..services.update import apply_update

    apply_update(settings)
    from ..services.update import manager

    return UpdateStatusOut(**manager.status())


def _is_newer(latest: str, current: str) -> bool:
    from ..services.update_engine import SemVer

    try:
        return SemVer.parse(latest) > SemVer.parse(current)
    except Exception:  # noqa: BLE001
        return False

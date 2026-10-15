"""Update channel client & staging manager (Phase 8 §3–§8).

Checks GitHub Releases for the newest ``latest.json`` (ETag-cached, rate-limit
aware, ``APP_UPDATE_URL`` override), validates it strictly (unknown
``schema_version`` → refuse), selects a delta / delta chain / full installer,
downloads the chosen package(s) with progress, verifies SHA-256 (and the
optional Ed25519 signature over ``latest.json``) *before* anything is staged,
and drives the transactional updater helper on Windows.

Never embeds tokens — anonymous public-repository access only.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from .errors import DomainError
from .update_engine import (
    DeltaRef,
    LatestManifest,
    SelectionKind,
    SemVer,
    SemVerError,
    UpdateEvent,
    UpdateRun,
    UpdateSchemaError,
    VerificationError,
    parse_latest,
    select_update,
    sha256_bytes,
    verify_latest_signature,
)

GITHUB_API = "https://api.github.com"

RATE_LIMIT_FA = "تعداد درخواست‌ها بیش از حد مجاز است؛ لطفاً کمی بعد دوباره تلاش کنید."
UNREACHABLE_FA = "دسترسی به منبع به‌روزرسانی ممکن نشد."
SCHEMA_REFUSE_FA = "ساختار پیام به‌روزرسانی شناخته نشد؛ لطفاً نصب دستی را انجام دهید."
NO_DELTA_FA = "بستهٔ تفاضلی موجود نیست؛ نصب کامل دانلود می‌شود."
UPDATER_MISSING_FA = (
    "برنامهٔ به‌روزرسان روی این نصب پیدا نشد؛ لطفاً فایل نصب کامل VIRA-Setup را "
    "دانلود و دستی اجرا کنید."
)
UNKNOWN_CURRENT_FA = (
    "نسخهٔ نصب‌شدهٔ فعلی قابل تشخیص نیست، پس تفاضل‌گیری ممکن نیست. لطفاً فایل نصب "
    "کامل (Setup) را دانلود و اجرا کنید؛ از آن پس نسخهٔ برنامه درست گزارش می‌شود و "
    "به‌روزرسانی فقط بخش‌های تغییرکرده را می‌گیرد."
)


class UpdateChannelError(Exception):
    """Channel-level failure with a user-facing Persian reason."""

    def __init__(self, reason_fa: str, *, status: int | None = None) -> None:
        super().__init__(reason_fa)
        self.reason_fa = reason_fa
        self.status = status


@dataclass
class ChannelResult:
    manifest: LatestManifest
    raw: bytes
    signature: bytes | None


# --------------------------------------------------------------- ETag cache ---

_etag_cache: dict[str, tuple[str | None, bytes]] = {}
_cache_lock = threading.Lock()


def _conditional_get(url: str, *, timeout: float = 8.0) -> tuple[int, bytes]:
    """GET with If-None-Match; 304 returns cached bytes. Raises UpdateChannelError."""
    import httpx

    headers = {"User-Agent": "VIRA-Updater", "Accept": "application/vnd.github+json"}
    with _cache_lock:
        cached = _etag_cache.get(url)
    if cached and cached[0]:
        headers["If-None-Match"] = cached[0]
    try:
        resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise UpdateChannelError(UNREACHABLE_FA) from exc
    if resp.status_code == 304 and cached:
        return 304, cached[1]
    if resp.status_code in (403, 429):
        raise UpdateChannelError(RATE_LIMIT_FA, status=resp.status_code)
    if resp.status_code >= 400:
        raise UpdateChannelError(UNREACHABLE_FA, status=resp.status_code)
    body = resp.content
    with _cache_lock:
        _etag_cache[url] = (resp.headers.get("ETag"), body)
    return resp.status_code, body


def fetch_channel(settings: Settings) -> ChannelResult:
    """Fetch + validate the newest latest.json (§3)."""
    override = (settings.app_update_url or "").strip()
    signature: bytes | None = None
    if override:
        status, raw = _conditional_get(override)
    else:
        # GitHub API first (rate-limit + ETag aware), then the immutable asset.
        api_url = f"{GITHUB_API}/repos/{settings.update_github_repo}/releases/latest"
        try:
            status, api_raw = _conditional_get(api_url)
        except UpdateChannelError:
            raise
        try:
            meta = json.loads(api_raw)
        except json.JSONDecodeError as exc:
            raise UpdateChannelError(UNREACHABLE_FA) from exc
        assets = meta.get("assets") or []
        asset_url = ""
        sig_url = ""
        for a in assets:
            name = str(a.get("name", ""))
            if name == "latest.json":
                asset_url = str(a.get("browser_download_url", ""))
            if name == "latest.json.sig":
                sig_url = str(a.get("browser_download_url", ""))
        if not asset_url:
            # fall back to the stable alias for repos that skip the asset step
            asset_url = (
                f"https://github.com/{settings.update_github_repo}"
                "/releases/latest/download/latest.json"
            )
        status, raw = _conditional_get(asset_url)
        del status
        if sig_url:
            try:
                _, signature = _conditional_get(sig_url)
            except UpdateChannelError:
                signature = None
    try:
        manifest = parse_latest(raw)
    except UpdateSchemaError as exc:
        raise UpdateChannelError(SCHEMA_REFUSE_FA) from exc
    # Ed25519 verification when a public key is baked in (§8 recommended)
    pub = _public_key_pem(settings)
    if pub is not None and signature is not None:
        try:
            verify_latest_signature(raw, signature, pub)
        except VerificationError as exc:
            raise UpdateChannelError(SCHEMA_REFUSE_FA) from exc
    return ChannelResult(manifest=manifest, raw=raw, signature=signature)


def _public_key_pem(settings: Settings) -> bytes | None:
    src = (settings.update_public_key or "").strip()
    if not src:
        return None
    if src.startswith("-----BEGIN"):
        return src.encode("utf-8")
    p = Path(src)
    return p.read_bytes() if p.is_file() else None


# ------------------------------------------------------------- check result ---


@dataclass
class PackageChoice:
    kind: str  # delta | delta_chain | full
    packages: list[dict[str, Any]] = field(default_factory=list)
    total_bytes: int = 0


@dataclass
class UpdateCheckResult:
    current: str
    latest: str | None
    update_available: bool
    checked: bool
    reason_fa: str | None = None
    notes_fa: str = ""
    notes_en: str = ""
    min_app_version: str = ""
    manual_required: bool = False
    choice: PackageChoice | None = None


def _parse_current(cur: str) -> SemVer | None:
    """Parse the running version, or ``None`` when it cannot be compared.

    Installs built before the provenance fix report ``0.0.0-unknown``; the update
    check must degrade to a full manual install there instead of raising.
    """
    try:
        return SemVer.parse(cur)
    except (SemVerError, ValueError):
        return None


def _full_package_choice(m: LatestManifest, cur: str) -> PackageChoice:
    """The full installer as a selectable package (no delta base available)."""
    return PackageChoice(
        kind="full",
        packages=[
            {
                "url": m.full_installer.url,
                "sha256": m.full_installer.sha256,
                "size": m.full_installer.size,
                "from_version": cur,
            }
        ],
        total_bytes=m.full_installer.size,
    )


def check_for_update(current: str, settings: Settings) -> UpdateCheckResult:
    cur = current.lstrip("v")
    try:
        channel = fetch_channel(settings)
    except UpdateChannelError as exc:
        return UpdateCheckResult(cur, None, False, False, reason_fa=exc.reason_fa)
    m = channel.manifest
    try:
        latest = SemVer.parse(m.version)
    except (SemVerError, ValueError):
        return UpdateCheckResult(cur, None, False, True, reason_fa=SCHEMA_REFUSE_FA)
    run = _parse_current(cur)
    if run is None:
        # An unstamped install (e.g. «0.0.0-unknown») has no comparable base: a
        # delta can never be applied, so offer the full installer instead.
        # Reporting this is far better than the 500 the user saw in v1.0.4.
        return UpdateCheckResult(
            cur,
            m.version,
            True,
            True,
            reason_fa=UNKNOWN_CURRENT_FA,
            notes_fa=m.notes_fa,
            notes_en=m.notes_en,
            min_app_version=m.min_app_version,
            manual_required=True,
            choice=_full_package_choice(m, cur),
        )
    if latest <= run:
        return UpdateCheckResult(
            cur, m.version, False, True, notes_fa=m.notes_fa, notes_en=m.notes_en,
            min_app_version=m.min_app_version,
        )
    # min_app_version gate: too-old installs must do a manual full install
    try:
        if run < SemVer.parse(m.min_app_version):
            return UpdateCheckResult(
                cur, m.version, True, True, notes_fa=m.notes_fa, notes_en=m.notes_en,
                min_app_version=m.min_app_version, manual_required=True,
                reason_fa=SCHEMA_REFUSE_FA,
            )
    except Exception:  # noqa: BLE001 - parse_latest already validated
        pass
    refs = [
        DeltaRef(d.from_version, d.url, d.sha256, d.size, to_version=m.version)
        for d in m.deltas
    ]
    try:
        choice = select_update(
            cur, m.version, refs,
            full_url=m.full_installer.url,
            full_size=m.full_installer.size,
        )
    except (SemVerError, ValueError):
        # No reconstructible delta path — never leave the user empty-handed.
        return UpdateCheckResult(
            cur,
            m.version,
            True,
            True,
            reason_fa=NO_DELTA_FA,
            notes_fa=m.notes_fa,
            notes_en=m.notes_en,
            min_app_version=m.min_app_version,
            manual_required=True,
            choice=_full_package_choice(m, cur),
        )
    return UpdateCheckResult(
        cur,
        m.version,
        True,
        True,
        notes_fa=m.notes_fa,
        notes_en=m.notes_en,
        min_app_version=m.min_app_version,
        choice=_package_choice(choice, m, cur),
    )


def _package_choice(choice: Any, m: LatestManifest, cur: str) -> PackageChoice:
    if choice.kind is SelectionKind.FULL:
        return PackageChoice(
            kind="full",
            packages=[{
                "url": m.full_installer.url,
                "sha256": m.full_installer.sha256,
                "size": m.full_installer.size,
                "from_version": cur,
            }],
            total_bytes=m.full_installer.size,
        )
    return PackageChoice(
        kind=choice.kind.value,
        packages=[
            {"url": d.url, "sha256": d.sha256, "size": d.size, "from_version": d.from_version}
            for d in choice.deltas
        ],
        total_bytes=choice.total_bytes,
    )


# ------------------------------------------------------ staging + download ---


@dataclass
class UpdateJob:
    state: str = "idle"  # idle|downloading|verifying|staged|applying|committed|rolled_back|failed
    total_bytes: int = 0
    downloaded_bytes: int = 0
    verified: bool = False
    staged_path: str = ""
    log_path: str = ""
    error_fa: str | None = None
    run: UpdateRun = field(default_factory=UpdateRun)


class UpdateManager:
    """One update job at a time (the updater helper also takes a mutex, §6)."""

    def __init__(self) -> None:
        self._job = UpdateJob()
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            j = self._job
            return {
                "state": j.state,
                "total_bytes": j.total_bytes,
                "downloaded_bytes": j.downloaded_bytes,
                "verified": j.verified,
                "staged_path": j.staged_path,
                "log_path": j.log_path,
                "error_fa": j.error_fa,
                "machine_state": j.run.state.value,
            }

    def start_download(self, check: UpdateCheckResult, settings: Settings) -> dict[str, Any]:
        import httpx

        with self._lock:
            if self._job.state in ("downloading", "verifying", "applying"):
                raise DomainError("به‌روزرسانی دیگری در حال اجرا است")
            if check.choice is None:
                raise DomainError("بستهٔ به‌روزرسانی انتخاب نشده است")
            version = check.latest or "unknown"
            staging = self._staging_dir(settings, version)
            staging.mkdir(parents=True, exist_ok=True)
            self._job = UpdateJob(state="downloading", total_bytes=check.choice.total_bytes)
            self._job.run.fire(UpdateEvent.START)
            pkgs = check.choice.packages
        log_path = staging / "update.log"
        try:
            for pkg in pkgs:
                url = str(pkg["url"])
                dest = staging / url.rsplit("/", 1)[-1]
                data = bytearray()
                with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
                    if resp.status_code in (403, 429):
                        raise UpdateChannelError(RATE_LIMIT_FA, status=resp.status_code)
                    resp.raise_for_status()
                    for chunk in resp.iter_bytes(1 << 16):
                        data.extend(chunk)
                        with self._lock:
                            self._job.downloaded_bytes += len(chunk)
                payload = bytes(data)
                with self._lock:
                    self._job.state = "verifying"
                # verify BEFORE anything is written into the staging area (§8)
                expected = str(pkg["sha256"])
                if sha256_bytes(payload) != expected.lower():
                    raise VerificationError("SHA-256 mismatch")
                dest.write_bytes(payload)
            with self._lock:
                self._job.verified = True
                self._job.state = "staged"
                self._job.staged_path = str(staging)
                self._job.log_path = str(log_path)
                self._job.run.fire(UpdateEvent.STAGED)
            log_path.write_text(f"staged {version} -> {staging}\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - normalize to job failure
            with self._lock:
                self._job.state = "failed"
                self._job.error_fa = getattr(exc, "reason_fa", None) or "خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد."
            raise
        return self.status()

    @staticmethod
    def _staging_dir(settings: Settings, version: str) -> Path:
        if settings.data_dir is None:
            raise DomainError("data_dir is not configured")
        return Path(settings.data_dir) / "updates" / version


manager = UpdateManager()


def install_root(settings: Settings) -> Path | None:
    """``{app}`` — the directory the running application is installed in.

    ``None`` for a dev checkout. Used to find the updater and to tell it which
    installation to patch, so an update never depends on the registry record
    (hand-unzipped / portable installs have none).
    """
    from ..version import app_root

    return app_root()


def _updater_command(settings: Settings, staged_path: str) -> tuple[list[str], Path]:
    """Locate the transactional updater and build its argv.

    Search order: the staging directory (deltas ship the helper from v1.0.5 on)
    → ``{app}\vira-updater.exe`` → next to the data directory → the shipped
    ``scripts\vira_updater.ps1`` through ``powershell.exe`` (unzipped portable
    installs, and the payload produced before the helper was compiled).
    """
    stage = Path(staged_path)
    log_path = stage / "update.log"
    root = install_root(settings)

    candidates = [stage / "vira-updater.exe"]
    if root is not None:
        candidates.append(root / "vira-updater.exe")
    if settings.data_dir is not None:
        candidates.append(Path(settings.data_dir).parent / "vira-updater.exe")
    for exe in candidates:
        if exe.is_file():
            # Single-dash PowerShell parameter names: «--name» is not a
            # parameter prefix for every PowerShell host, and the helper is a
            # PowerShell script compiled to an exe (ps2exe).
            argv = [str(exe), "-stage", str(stage), "-log", str(log_path)]
            if root is not None:
                argv += ["-InstallDir", str(root)]
            return argv, log_path

    if root is not None:
        script = root / "scripts" / "vira_updater.ps1"
        if script.is_file():
            argv = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Stage",
                str(stage),
                "-Log",
                str(log_path),
                "-InstallDir",
                str(root),
            ]
            return argv, log_path
    raise DomainError(UPDATER_MISSING_FA)


def launch_updater(settings: Settings, staged_path: str) -> dict[str, Any]:
    """Launch the transactional updater helper (Windows: vira-updater.exe). §6."""
    if os.name != "nt":
        raise DomainError("اجرای به‌روزرسانی خودکار فقط در ویندوز در دسترس است")
    import subprocess

    argv, log_path = _updater_command(settings, staged_path)
    with manager._lock:  # noqa: SLF001 - module-private manager
        manager._job.state = "applying"
    subprocess.Popen(argv, close_fds=True)  # noqa: S603 - fixed argv, no shell
    _ = log_path
    return manager.status()


def apply_update(settings: Settings) -> dict[str, Any]:
    """Pre-update SQLite backup (§7) then launch the updater helper."""
    backup_note = ""
    status = manager.status()
    if status["state"] != "staged":
        raise DomainError("ابتدا بستهٔ به‌روزرسانی را دانلود کنید")
    if settings.data_dir is not None and settings.sqlite_database_path is not None and Path(settings.sqlite_database_path).is_file():
        backups = Path(settings.data_dir) / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        target = backups / f"pre-update-{time.strftime('%Y%m%d-%H%M%S')}.sqlite3"
        target.write_bytes(Path(settings.sqlite_database_path).read_bytes())
        backup_note = str(target)
    out = launch_updater(settings, str(status["staged_path"]))
    out["pre_update_backup"] = backup_note
    return out


__all__ = [
    "ChannelResult",
    "PackageChoice",
    "UpdateChannelError",
    "UpdateCheckResult",
    "UpdateManager",
    "apply_update",
    "check_for_update",
    "fetch_channel",
    "install_root",
    "launch_updater",
    "manager",
]

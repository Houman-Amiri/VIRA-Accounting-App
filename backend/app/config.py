"""Validated runtime configuration (pydantic-settings).

Secrets come from environment variables (or Windows Credential Manager in
production) — never from the repository or the database.  The SQLite file
defaults to ``%LOCALAPPDATA%\\VIRA\\data\\vira.sqlite3`` on Windows and to the
platform data dir elsewhere (dev/CI), always configurable via
``SQLITE_DATABASE_PATH``.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    if os.name == "nt":  # pragma: no cover - windows only
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "VIRA"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "VIRA"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "VIRA Accounting"
    environment: str = Field(default="development")  # development|production
    bind_host: str = "127.0.0.1"
    bind_port: int = 8787

    # --- data locations (kept OUTSIDE the git repository) ---
    data_dir: Path | None = None
    sqlite_database_path: Path | None = None
    storage_provider: str = "local"  # local|s3
    receipt_dir: Path | None = None
    # --- S3-compatible storage (STORAGE_PROVIDER=s3; Phase 7 §2) ---
    s3_bucket: str = ""
    s3_endpoint_url: str = ""  # MinIO / R2 / B2 endpoint; empty = AWS
    s3_region: str = ""
    s3_sse: str = "AES256"  # server-side encryption on write

    # --- security ---
    session_secret: str = "dev-only-insecure-session-secret-change-me"
    app_encryption_key: str = ""  # required in production (Fernet key)
    session_ttl_seconds: int = 12 * 60 * 60
    csrf_cookie_name: str = "vira_csrf"
    session_cookie_name: str = "vira_session"
    frontend_origin: str = "http://localhost:5173"
    strict_secrets: bool = False  # set True in production (refuse weak secrets)

    # --- ledger / localization ---
    base_currency: str = "IRR"  # canonical stored unit: Rial (display default Toman)
    display_currency: str = "IRT"  # 1 Toman = 10 Rial, applied exactly once
    default_locale: str = "fa_IR"

    # --- external APIs ---
    frankfurter_base_url: str = "https://api.frankfurter.app"
    update_github_repo: str = "Houman-Amiri/VIRA-Accounting-App"

    # --- scheduler ---
    scheduler_enabled: bool = False

    @field_validator("sqlite_database_path", "receipt_dir", "data_dir", mode="before")
    @classmethod
    def _empty_path_to_none(cls, v: object) -> object:
        if v == "" or v is None:
            return None
        return v

    def model_post_init(self, __context: object) -> None:
        if self.data_dir is None:
            object.__setattr__(self, "data_dir", default_data_dir())
        data_dir = self.data_dir
        assert data_dir is not None
        if self.sqlite_database_path is None:
            object.__setattr__(
                self, "sqlite_database_path", data_dir / "data" / "vira.sqlite3"
            )
        if self.receipt_dir is None:
            object.__setattr__(self, "receipt_dir", data_dir / "receipt_storage")

    def validate_production_secrets(self) -> None:
        """Refuse to boot a production instance with missing/weak secrets."""
        if not (self.strict_secrets or self.environment == "production"):
            return
        problems: list[str] = []
        if len(self.session_secret) < 32 or "dev-only" in self.session_secret:
            problems.append("SESSION_SECRET is missing or weak (need >= 32 chars)")
        if not self.app_encryption_key:
            problems.append("APP_ENCRYPTION_KEY is required in production")
        else:
            from .security.envelope import EnvelopeError, build_envelope

            try:
                build_envelope(self.app_encryption_key)
            except EnvelopeError:
                problems.append("APP_ENCRYPTION_KEY must contain valid Fernet key(s)")
        if "*" in self.frontend_origin or not self.frontend_origin.startswith("http"):
            problems.append("FRONTEND_ORIGIN must be an explicit http(s) origin (no wildcards)")
        if problems:
            raise RuntimeError("Refusing to start: " + "; ".join(problems))

    def ensure_directories(self) -> None:
        assert self.data_dir is not None and self.sqlite_database_path is not None
        assert self.receipt_dir is not None
        self.sqlite_database_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipt_dir.mkdir(parents=True, exist_ok=True)


def load_settings(**overrides: object) -> Settings:
    settings = Settings(**overrides)  # type: ignore[arg-type]
    settings.validate_production_secrets()
    settings.ensure_directories()
    return settings

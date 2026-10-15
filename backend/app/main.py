"""FastAPI application factory — VIRA accounting backend.

Binds to 127.0.0.1 by default (LAN only via explicit setting).  Serves the
JSON REST API under ``/api/v1`` with OpenAPI/Swagger documentation; the built
React SPA is served from ``frontend/dist`` when present (Phase 6 wiring).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    accounts,
    auth,
    documents,
    fiscal,
    fx,
    health,
    imports,
    journal,
    reconciliation,
    reports,
    search,
)
from .api import api_keys as api_keys_api
from .api import (
    exports as exports_api,
)
from .api import system as system_api
from .api import (
    webhooks as webhooks_api,
)
from .api.errors import install_error_handlers
from .config import Settings, load_settings
from .db import Database
from .security.session import SessionManager
from .services.scheduler import SchedulerManager

log = logging.getLogger(__name__)


def spa_static_dir(module_file: Path | None = None) -> Path | None:
    """Locate the built SPA. Works in the dev checkout AND the installed payload.

    * ``VIRA_STATIC_DIR`` env — explicit override
    * ``<install>/static`` — installed payload (``{app}/app/main.py`` → ``{app}/static``)
    * ``<repo>/frontend/dist`` — dev checkout (``<repo>/backend/app/main.py``)
    """
    import os

    here = (module_file or Path(__file__)).resolve()
    candidates = [
        Path(os.environ["VIRA_STATIC_DIR"]) if os.environ.get("VIRA_STATIC_DIR") else None,
        here.parents[1] / "static",           # installed: {app}/static
        here.parents[2] / "frontend" / "dist",  # dev: <repo>/frontend/dist
    ]
    for c in candidates:
        if c is not None and c.is_dir():
            return c
    return None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    # Structured logging with mandatory sensitive-field redaction (Phase 5 §9).
    from .security.redact import install_structlog

    install_structlog()
    # Native rotating file logs (Phase 6 §9).
    from .logging_setup import install_file_logging

    assert settings.data_dir is not None
    install_file_logging(settings.data_dir)
    database = Database(settings)
    session_manager = SessionManager(
        settings.session_secret,
        ttl_seconds=settings.session_ttl_seconds,
        secure=settings.environment == "production",
    )
    scheduler: SchedulerManager | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal scheduler
        pragmas = database.verify()
        log.info("SQLite pragmas verified: %s", pragmas)
        if settings.scheduler_enabled:
            scheduler = SchedulerManager(database.session_factory)
            scheduler.start()
        app.state.scheduler = scheduler  # surfaced by /health/ready + /system/status
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown()
            app.state.scheduler = None
            database.dispose()

    app = FastAPI(
        title="VIRA Accounting API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.database = database
    app.state.session_manager = session_manager

    origins = [settings.frontend_origin]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Sudo-Token", "X-API-Key"],
    )

    # --- hardened security headers (Phase 5 §8) ---
    from starlette.datastructures import MutableHeaders

    class SecurityHeadersMiddleware:
        """Pure-ASGI middleware (BaseHTTPMiddleware interferes with FastAPI
        exception handlers, so we sit in the stack without wrapping responses)."""

        def __init__(self, app):  # type: ignore[no-untyped-def]
            self.app = app

        async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            async def send_with_headers(message):  # type: ignore[no-untyped-def]
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers.setdefault("X-Frame-Options", "DENY")
                    headers.setdefault("X-Content-Type-Options", "nosniff")
                    headers.setdefault("Referrer-Policy", "same-origin")
                    headers.setdefault(
                        "Content-Security-Policy",
                        "default-src 'self'; img-src 'self' data: blob:; "
                        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                        "frame-ancestors 'none'; object-src 'none'",
                    )
                    if scope.get("scheme") == "https":
                        headers.setdefault(
                            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                        )
                await send(message)

            await self.app(scope, receive, send_with_headers)

    app.add_middleware(SecurityHeadersMiddleware)

    install_error_handlers(app)

    # --- auditor role is read-only on every mutating route (Phase 5 §2) ---
    from .api.deps import auditor_read_only

    app.include_router(health.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(auth.router)
    app.include_router(accounts.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(journal.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(reports.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(imports.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(reconciliation.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(search.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(fx.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(documents.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(api_keys_api.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(system_api.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(fiscal.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(webhooks_api.router)
    app.include_router(exports_api.router, dependencies=[Depends(auditor_read_only)])

    dist = spa_static_dir()
    if dist is not None:  # pragma: no cover - frontend build
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app


app = create_app()

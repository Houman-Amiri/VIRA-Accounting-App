"""FastAPI application factory — VIRA accounting backend.

Binds to 127.0.0.1 by default (LAN only via explicit setting).  Serves the
JSON REST API under ``/api/v1`` with OpenAPI/Swagger documentation; the built
React SPA is served from ``frontend/dist`` when present (Phase 6 wiring).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import accounts, auth, documents, fx, health, imports, journal, reports
from .api.errors import install_error_handlers
from .config import Settings, load_settings
from .db import Database
from .security.session import SessionManager
from .services.scheduler import SchedulerManager

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
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
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown()
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
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )

    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(journal.router)
    app.include_router(reports.router)
    app.include_router(imports.router)
    app.include_router(fx.router)
    app.include_router(documents.router)

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():  # pragma: no cover - frontend build
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app


app = create_app()

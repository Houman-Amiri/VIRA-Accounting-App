"""FastAPI application factory — VIRA accounting backend.

Binds to 127.0.0.1 by default (LAN only via explicit setting).  Serves the
JSON REST API under ``/api/v1`` with OpenAPI/Swagger documentation; the built
React SPA is served from ``frontend/dist`` when present (Phase 6 wiring).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from os import PathLike
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

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
from .api import calendar as calendar_api
from .api import (
    exports as exports_api,
)
from .api import (
    operations as operations_api,
)
from .api import pricing as pricing_api
from .api import system as system_api
from .api import (
    webhooks as webhooks_api,
)
from .api.errors import install_error_handlers
from .config import Settings, load_settings
from .db import Database
from .security.session import SessionManager
from .services import private_source_channel
from .services.pdf_rendering import PdfRenderer, PrivatePdfPolicy
from .services.scheduler import SchedulerManager
from .version import app_root

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
        here.parents[1] / "static",  # installed: {app}/static
        here.parents[2] / "frontend" / "dist",  # dev: <repo>/frontend/dist
    ]
    for c in candidates:
        if c is not None and c.is_dir():
            return c
    return None


def create_app(
    settings: Settings | None = None, *, private_pdf_policy: PrivatePdfPolicy | None = None
) -> FastAPI:
    renderer = PdfRenderer(private_pdf_policy)
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
    update_lock = settings.data_dir / "updates" / ".update.lock"
    # Authenticate private ownership once at factory startup, while the installed
    # manifest/anchor agree. Never re-read a partially replaced manifest merely
    # to decide whether a write should be quarantined.
    source_scope = private_source_channel.scope(settings, app_root())
    update_guards = [update_lock]
    if source_scope is not None:
        update_guards += [source_scope.home / ".native-channel.lock",
                          source_scope.home / ".native-update.lock"]

    def update_write_blocked() -> bool:
        return any(path.exists() or path.is_symlink() for path in update_guards)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal scheduler
        pragmas = database.verify()
        log.info("SQLite pragmas verified: %s", pragmas)
        if settings.scheduler_enabled:
            scheduler = SchedulerManager(database.session_factory, write_gate=update_write_blocked)
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
    app.state.pdf_renderer = renderer
    app.state.settings = settings
    app.state.database = database
    app.state.session_manager = session_manager
    app.state.update_write_blocked = update_write_blocked

    origins = [settings.frontend_origin]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-CSRF-Token",
            "Idempotency-Key",
            "X-Sudo-Token",
            "X-API-Key",
        ],
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

            # No user writes may be acknowledged in the target before the
            # updater commits: a subsequent schema rollback would discard them.
            # Health/status GETs remain available to the verified apply protocol.
            if scope.get("method") not in {"GET", "HEAD", "OPTIONS"} and update_write_blocked():
                from starlette.responses import JSONResponse

                response = JSONResponse(
                    {
                        "type": "urn:vira:error:update_in_progress",
                        "title": "Update in progress",
                        "status": 503,
                        "detail": "به‌روزرسانی در حال بررسی است؛ ثبت اطلاعات تا پایان آن متوقف است.",
                        "code": "update_in_progress",
                        "instance": scope.get("path", ""),
                    },
                    status_code=503,
                    headers={"Retry-After": "3"},
                )
                await response(scope, receive, send_with_headers)
                return
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
    app.include_router(calendar_api.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(pricing_api.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(system_api.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(fiscal.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(webhooks_api.router)
    app.include_router(exports_api.router, dependencies=[Depends(auditor_read_only)])
    app.include_router(operations_api.warehouse, dependencies=[Depends(auditor_read_only)])
    app.include_router(operations_api.orders, dependencies=[Depends(auditor_read_only)])
    app.include_router(operations_api.production, dependencies=[Depends(auditor_read_only)])

    dist = spa_static_dir()
    if dist is not None:
        _mount_spa(app, Path(dist))

    return app


# ---------------------------------------------------------------- SPA mount ---
class _ImmutableAssets(StaticFiles):
    """Vite hashes asset filenames, so they may be cached hard."""

    def file_response(  # type: ignore[override]
        self,
        full_path: str | PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        if stat_result is not None:
            response.headers["cache-control"] = "public, max-age=31536000, immutable"
        return response


def _spa_headers(spa_build: str) -> dict[str, str]:
    headers = {"cache-control": "no-store, must-revalidate", "pragma": "no-cache"}
    if spa_build:
        headers["x-vira-spa-build"] = spa_build
    return headers


def _mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA so an upgraded install can never serve an old UI.

    v1.0.5 shipped fresh bundles but the browser kept its cached ``index.html``
    (no ``Cache-Control`` at all) while the installer left the previous hashed
    bundles in ``{app}\\static`` — users saw the *old* interface after a
    successful upgrade. The shell is now served ``no-store``, hashed assets are
    ``immutable``, and unknown non-API paths fall back to the shell (so
    ``/warehouse`` deep links work).
    """
    from .version import version_info  # local import: avoids a cycle at startup

    index = dist / "index.html"
    spa_build = str(version_info().get("spa_build") or "")
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", _ImmutableAssets(directory=str(assets)), name="spa-assets")

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa_shell(full_path: str) -> Response:
        if full_path.startswith("api/"):
            # Unknown API paths must stay JSON 404s, never the SPA shell.
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate, headers={"cache-control": "no-cache"})
        return FileResponse(index, media_type="text/html", headers=_spa_headers(spa_build))


app = create_app()

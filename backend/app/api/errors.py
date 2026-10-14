"""Global error handling — RFC 9457 Problem Details (application/problem+json)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services.errors import DomainError


def _problem(
    *, type_: str, title: str, status: int, detail: str, instance: str, code: str | None,
    errors: list[dict] | None = None,
) -> JSONResponse:
    body = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "instance": instance,
        "code": code,
        "errors": errors or [],
    }
    return JSONResponse(
        status_code=status, content=body, media_type="application/problem+json"
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(
            type_=f"urn:vira:error:{exc.code}",
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            instance=str(request.url.path),
            code=exc.code,
            errors=exc.errors,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        return _problem(
            type_="urn:vira:error:validation_error",
            title="Request validation failed",
            status=422,
            detail="one or more fields are invalid",
            instance=str(request.url.path),
            code="validation_error",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return _problem(
            type_="urn:vira:error:internal",
            title="Internal server error",
            status=500,
            detail=str(exc),
            instance=str(request.url.path),
            code="internal_error",
        )


class HealthPayload(BaseModel):
    status: str
    sqlite_version: str
    pragmas: dict[str, str]
    alembic_revision: str | None = None
    invariants: dict[str, object] | None = None

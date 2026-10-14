"""Resilient outbound HTTP adapters (Phase 5 §6).

All external calls (Frankfurter FX, Open-Banking providers, optional Vision
LLM) go through these adapters: strict connect/read timeouts, exponential
backoff with jitter (tenacity), and ``Retry-After`` respect on 429/503.
Async adapter for the FastAPI request path; sync adapter for the scheduler.
"""

from __future__ import annotations

import contextlib
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_ATTEMPTS = 4


class ExternalServiceError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, ExternalServiceError):
        return exc.status in (429, 500, 502, 503, 504)
    return False


def _retry_after(state: RetryCallState) -> float:
    """Honor Retry-After when the failure carried one; else jittered expo."""
    exc = state.outcome.exception() if state.outcome else None
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return min(float(retry_after), 60.0) + random.uniform(0, 0.25)
    return min(2.0 * (2 ** (state.attempt_number - 1)), 30.0) + random.uniform(0, 0.5)


@dataclass
class ExternalResponse:
    status: int
    json_body: Any
    headers: dict[str, str]


async def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    timeout: float = 10.0,
) -> ExternalResponse:
    """Async GET/POST with retries, backoff+jitter and Retry-After support."""

    async def _once() -> ExternalResponse:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout))
        ) as client:
            resp = await client.request(method, url, headers=headers, json=json_body)
            if resp.status_code == 429 or resp.status_code >= 500:
                exc = ExternalServiceError(
                    f"{url} returned {resp.status_code}", status=resp.status_code
                )
                ra = resp.headers.get("Retry-After")
                if ra is not None:
                    with contextlib.suppress(ValueError):
                        exc.retry_after = float(ra)  # type: ignore[attr-defined]
                raise exc
            return ExternalResponse(
                status=resp.status_code,
                json_body=resp.json() if resp.content else None,
                headers=dict(resp.headers),
            )

    async for attempt in AsyncRetrying(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=_retry_after,  # type: ignore[arg-type]
        reraise=True,
    ):
        with attempt:
            return await _once()
    raise ExternalServiceError(f"exhausted retries for {url}")  # pragma: no cover


def request_json_sync(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    timeout: float = 10.0,
    max_attempts: int = MAX_ATTEMPTS,
) -> ExternalResponse:
    """Sync variant (scheduler jobs) — same policy: timeouts + backoff."""
    from tenacity import Retrying

    def _once() -> ExternalResponse:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(5.0, timeout))) as client:
            resp = client.request(method, url, headers=headers, json=json_body)
            if resp.status_code == 429 or resp.status_code >= 500:
                exc = ExternalServiceError(
                    f"{url} returned {resp.status_code}", status=resp.status_code
                )
                ra = resp.headers.get("Retry-After")
                if ra is not None:
                    with contextlib.suppress(ValueError):
                        exc.retry_after = float(ra)  # type: ignore[attr-defined]
                raise exc
            return ExternalResponse(
                status=resp.status_code,
                json_body=resp.json() if resp.content else None,
                headers=dict(resp.headers),
            )

    for attempt in Retrying(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(max_attempts),
        wait=_retry_after,  # type: ignore[arg-type]
        reraise=True,
    ):
        with attempt:
            return _once()
    raise ExternalServiceError(f"exhausted retries for {url}")  # pragma: no cover


def now_with_jitter(base: float) -> float:  # small helper kept for tests
    return base + random.uniform(0, 0.05) + time.time() * 0

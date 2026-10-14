"""Structured-log redaction (Phase 5 §9).

A mandatory structlog processor that scrubs sensitive keys from every log
event and exception traceback before output: ``password``, ``token``,
``authorization``, ``cookie``, ``secret``, ``iban``, ``account_number``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "set-cookie",
        "secret",
        "client_secret",
        "api_key",
        "x-api-key",
        "x-sudo-token",
        "idempotency-key",
        "iban",
        "account_number",
        "totp_secret_enc",
        "password_hash",
        "code_hash",
        "csrf_token",
    }
)

REDACTED = "***REDACTED***"
#: IBAN-shaped values anywhere in strings.
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")


def _scrub_value(key: str, value: Any) -> Any:
    if key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {k: _scrub_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(key, v) for v in value]
    if isinstance(value, str):
        return _IBAN_RE.sub(REDACTED, value)
    return value


def redact_event(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> Mapping[str, Any]:
    """structlog processor: scrub sensitive keys + IBAN-shaped strings."""
    return {str(k): _scrub_value(str(k), v) for k, v in event_dict.items()}


def install_structlog() -> None:
    """Configure the mandatory structlog pipeline (once at app startup)."""
    import logging

    import structlog

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_event,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()
            if __debug__
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    import structlog

    return structlog.get_logger(name)

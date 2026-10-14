"""Identifier helpers — UUIDv7 (canonical TEXT storage) and audit timestamps."""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import UTC, datetime


def uuid7() -> str:
    """Generate a UUIDv7 (time-ordered) as a canonical lowercase hex string.

    Layout (128 bits): 48-bit unix-ms timestamp | version 7 (4 bits) |
    12 random bits | variant ``10`` (2 bits) | 62 random bits.
    Implemented locally because the stdlib lacks uuid7 on Python < 3.13.
    """
    ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    return str(uuid.UUID(int=value))


def utc_now_iso() -> str:
    """UTC timestamp as ISO-8601 with ``Z`` suffix (canonical storage form)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def today_iso() -> str:
    """Current UTC accounting date (``YYYY-MM-DD``)."""
    return datetime.now(UTC).date().isoformat()

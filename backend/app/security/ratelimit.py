"""Token-bucket rate limiting (Phase 5 §8).

In-process token buckets keyed by ``(scope, identity)`` — IP for anonymous
routes, account for login attempts.  The login bucket implements exponential
lockout: after ``max_attempts`` within the window, each further attempt extends
the lockout.  No external service (Windows-native, single-process deployment).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    tokens: float
    updated: float
    failures: int = 0
    locked_until: float = 0.0


@dataclass
class RateLimiter:
    rate_per_minute: float = 5.0
    burst: float = 5.0
    base_lockout_seconds: float = 30.0
    _buckets: dict[tuple[str, str], _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, scope: str, identity: str, *, now: float | None = None) -> bool:
        """Consume one token; False when throttled or locked out."""
        current = now if now is not None else time.time()
        key = (scope, identity)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.burst, updated=current)
                self._buckets[key] = bucket
            if current < bucket.locked_until:
                return False
            elapsed = max(0.0, current - bucket.updated)
            bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate_per_minute / 60.0)
            bucket.updated = current
            if bucket.tokens < 1.0:
                return False
            bucket.tokens -= 1.0
            return True

    def register_failure(self, scope: str, identity: str, *, now: float | None = None) -> float:
        """Record an auth failure; returns the lockout-until timestamp."""
        current = now if now is not None else time.time()
        key = (scope, identity)
        with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket(tokens=self.burst, updated=current))
            bucket.failures += 1
            if bucket.failures >= int(self.burst):
                lock = self.base_lockout_seconds * (2 ** (bucket.failures - int(self.burst)))
                bucket.locked_until = current + lock
            return bucket.locked_until

    def register_success(self, scope: str, identity: str) -> None:
        with self._lock:
            key = (scope, identity)
            bucket = self._buckets.get(key)
            if bucket is not None:
                bucket.failures = 0
                bucket.locked_until = 0.0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


#: Shared limiter for auth + heavy endpoints.
limiter = RateLimiter(rate_per_minute=5.0, burst=5.0)


def client_ip(request: object) -> str:
    client = getattr(request, "client", None)
    return str(getattr(client, "host", "unknown")) if client is not None else "unknown"

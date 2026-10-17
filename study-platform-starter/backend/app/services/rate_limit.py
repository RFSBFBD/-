"""Lightweight in-memory sliding-window rate limiter.

Single-process only; sufficient for the current single-service deployment. A
shared store (Redis) replaces this when the app scales horizontally.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.config import settings


class RateLimitExceeded(Exception):
    status_code = 429

    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded. Try again shortly.")
        self.retry_after = retry_after


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self._limit = limit
        self._window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                retry_after = max(1, int(bucket[0] + self._window - now) + 1)
                raise RateLimitExceeded(retry_after)
            bucket.append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


_upload_limiter = InMemoryRateLimiter(settings.upload_rate_limit_per_minute)


def get_upload_limiter() -> InMemoryRateLimiter:
    return _upload_limiter


__all__ = ["InMemoryRateLimiter", "RateLimitExceeded", "get_upload_limiter"]

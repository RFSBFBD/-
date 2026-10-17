"""Server-authoritative clock.

All study-session timing is derived from this module. Tests may monkeypatch
``utcnow`` to simulate expiry without waiting.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize a possibly-naive datetime (e.g. from SQLite) to UTC-aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["as_utc", "utcnow"]

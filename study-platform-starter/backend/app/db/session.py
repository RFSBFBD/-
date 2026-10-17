"""Database engine and session management.

Uses synchronous SQLAlchemy 2.0 with the psycopg (v3) driver. Database work is
performed in FastAPI's threadpool via regular ``def`` endpoints/dependencies,
keeping the async event loop free for external I/O.

The engine is created lazily so that the application can boot in local mode
without a database configured. Tests override ``get_db`` with an isolated
session, so no real database is required for the unit suite.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _session_factory


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose cached engine/factory (used by tests and configuration changes)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


__all__ = ["get_db", "get_engine", "get_session_factory", "reset_engine"]

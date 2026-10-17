"""Dialect-aware embedding column type.

On PostgreSQL it maps to ``pgvector``'s ``vector(dim)`` so similarity search can
run in the database. On other dialects (SQLite for tests) it stores a JSON list,
letting the same models and services run everywhere.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator


class Vector(TypeDecorator[Any]):
    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector as PgVector

                return dialect.type_descriptor(PgVector(self.dimensions))
            except ImportError:  # pragma: no cover - pgvector installed in prod
                return dialect.type_descriptor(Text())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return list(value)


__all__ = ["Vector"]

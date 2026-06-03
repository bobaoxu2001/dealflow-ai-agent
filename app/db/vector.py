"""Portable embedding column type.

On PostgreSQL we use the native pgvector `Vector` type so we get real
ANN/cosine operators (`<=>`). On SQLite (local/test) we transparently fall back
to a JSON-encoded list of floats, and similarity is computed in Python. This
lets the *same* models and tests run with or without Postgres.
"""
from __future__ import annotations

import json

from sqlalchemy.types import Text, TypeDecorator

from app.utils.config import settings

try:  # pgvector is always in requirements, but guard the import defensively.
    from pgvector.sqlalchemy import Vector as _PGVector

    _HAS_PGVECTOR = True
except Exception:  # pragma: no cover - only if pgvector missing
    _PGVector = None
    _HAS_PGVECTOR = False


class JSONVector(TypeDecorator):
    """Stores a list[float] as JSON text. Used as the SQLite fallback."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


def embedding_column_type(dim: int = None):
    """Return the appropriate column type for the active database."""
    dim = dim or settings.embedding_dim
    if settings.is_postgres and _HAS_PGVECTOR:
        # Native pgvector column with a JSON variant so metadata reflection is safe.
        return _PGVector(dim).with_variant(JSONVector(), "sqlite")
    return JSONVector()

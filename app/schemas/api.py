"""Shared / generic API schemas."""
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    environment: str
    database: str
    embedding_provider: str


class ErrorResponse(BaseModel):
    detail: str

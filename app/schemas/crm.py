"""CRM / search API schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VectorSearchRequest(BaseModel):
    query: str = Field(..., description="Free-text query to embed and search.")
    account_id: str | None = Field(default=None, description="Restrict to one account.")
    opportunity_id: str | None = Field(default=None, description="Restrict to one opportunity.")
    top_k: int = Field(default=5, ge=1, le=50)


class SearchHitModel(BaseModel):
    id: int
    source_type: str
    source_id: str | None = None
    account_id: str | None = None
    opportunity_id: str | None = None
    content: str
    score: float
    metadata: dict[str, Any] = {}


class VectorSearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchHitModel]


class ContextResponse(BaseModel):
    structured: dict[str, Any]
    documents: list[SearchHitModel]

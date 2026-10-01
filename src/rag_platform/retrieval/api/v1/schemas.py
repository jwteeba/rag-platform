"""Request/response schemas for the retrieval API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=100)
    document_ids: list[uuid.UUID] | None = None


class SearchResultResponse(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    score: float
    chunk_index: int


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]

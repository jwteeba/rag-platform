"""Request/response schemas for the generation API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PromptTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    system_prompt: str = Field(..., min_length=1)
    user_template: str = Field(..., min_length=1)
    model_target: str = Field(..., min_length=1, max_length=100)


class PromptTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, min_length=1)
    user_template: str | None = Field(default=None, min_length=1)
    model_target: str | None = Field(default=None, min_length=1, max_length=100)


class PromptTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    system_prompt: str
    user_template: str
    model_target: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptTemplateListResponse(BaseModel):
    items: list[PromptTemplateResponse]


class AssembleRequest(BaseModel):
    query: str = Field(..., min_length=1)
    chunks: list[ChunkInput]
    template_id: uuid.UUID | None = None


class ChunkInput(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    score: float
    chunk_index: int


class AssembledPromptResponse(BaseModel):
    system_prompt: str
    rendered_context: str
    user_query: str
    token_count: int
    source_chunks: list[SourceChunk]


class SourceChunk(BaseModel):
    filename: str
    chunk_index: int

"""Request and response schemas for the document_management API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from rag_platform.document_management.domain.entities import DocumentStatus


class DocumentResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    has_more: bool
    next_cursor: str | None = None


class DownloadUrlResponse(BaseModel):
    url: str

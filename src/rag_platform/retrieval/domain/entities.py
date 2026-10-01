"""Retrieval domain entities."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(slots=True)
class SearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    score: float
    chunk_index: int

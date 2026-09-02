"""Application-layer DTOs for document_management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


@dataclass(frozen=True, slots=True)
class UploadDocumentInput:
    owner_id: uuid.UUID
    filename: str
    content_type: str
    data: bytes

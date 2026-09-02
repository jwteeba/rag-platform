"""DocumentManagement domain entities.

Plain, framework-free Python — no FastAPI, no SQLAlchemy, no Pydantic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rag_platform.core.ids import generate_uuid7


@dataclass(slots=True)
class Document:
    """A document uploaded by a user.

    `storage_key` is the object path inside the bucket: `{id}/{filename}`.
    Derived at creation time and never mutated — if a file is re-uploaded
    it becomes a new Document with a new id.
    """

    id: uuid.UUID
    owner_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        owner_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> Document:
        doc_id = generate_uuid7()
        return cls(
            id=doc_id,
            owner_id=owner_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=f"{doc_id}/{filename}",
        )

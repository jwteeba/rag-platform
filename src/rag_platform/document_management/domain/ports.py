"""DocumentManagement domain ports.

Interfaces only. Infrastructure implementations live in
`document_management/infrastructure/`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from rag_platform.document_management.domain.entities import Document


class DocumentRepositoryPort(ABC):
    @abstractmethod
    async def add(self, document: Document) -> None: ...

    @abstractmethod
    async def get_by_id(self, document_id: uuid.UUID) -> Document | None: ...

    @abstractmethod
    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, after_id: uuid.UUID | None
    ) -> tuple[list[Document], bool]: ...

    @abstractmethod
    async def delete(self, document_id: uuid.UUID) -> None: ...


class ObjectStoragePort(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def presigned_download_url(self, key: str, *, expiry_seconds: int) -> str: ...

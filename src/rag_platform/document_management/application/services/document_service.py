"""Document use cases: upload, get, list, download URL, delete.

Orchestration only — validation, persistence, and storage are delegated to
ports. No framework imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_platform.core.logging import get_logger
from rag_platform.document_management.domain.entities import Document
from rag_platform.document_management.domain.exceptions import (
    DocumentNotFoundError,
    EmptyFileError,
    FileTooLargeError,
    UnsupportedContentTypeError,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from rag_platform.document_management.application.dto.document_dto import UploadDocumentInput
    from rag_platform.document_management.domain.ports import (
        DocumentRepositoryPort,
        ObjectStoragePort,
    )

logger = get_logger(__name__)


class DocumentService:
    def __init__(
        self,
        *,
        repository: DocumentRepositoryPort,
        storage: ObjectStoragePort,
        max_size_bytes: int,
        allowed_content_types: list[str],
        presigned_expiry_seconds: int,
        enqueue_storage_cleanup: Callable[[str], None] | None = None,
    ) -> None:
        self._repo = repository
        self._storage = storage
        self._max_size = max_size_bytes
        self._allowed_types = allowed_content_types
        self._expiry = presigned_expiry_seconds
        self._enqueue_storage_cleanup = enqueue_storage_cleanup

    async def upload(self, data: UploadDocumentInput) -> Document:
        if len(data.data) == 0:
            raise EmptyFileError()
        if len(data.data) > self._max_size:
            raise FileTooLargeError()
        if data.content_type not in self._allowed_types:
            raise UnsupportedContentTypeError()

        document = Document.create(
            owner_id=data.owner_id,
            filename=data.filename,
            content_type=data.content_type,
            size_bytes=len(data.data),
        )
        # Persist metadata first so a storage failure leaves no orphan row.
        # On storage failure the transaction rolls back and the row is gone.
        await self._repo.add(document)
        await self._storage.upload(document.storage_key, data.data, data.content_type)
        return document

    async def get(self, document_id: uuid.UUID, *, requester_id: uuid.UUID) -> Document:
        document = await self._repo.get_by_id(document_id)
        if document is None or document.owner_id != requester_id:
            raise DocumentNotFoundError()
        return document

    async def list_for_user(
        self, owner_id: uuid.UUID, *, limit: int, after_id: uuid.UUID | None
    ) -> tuple[list[Document], bool]:
        return await self._repo.list_for_owner(owner_id, limit=limit, after_id=after_id)

    async def get_download_url(self, document_id: uuid.UUID, *, requester_id: uuid.UUID) -> str:
        document = await self.get(document_id, requester_id=requester_id)
        return await self._storage.presigned_download_url(
            document.storage_key, expiry_seconds=self._expiry
        )

    async def delete(self, document_id: uuid.UUID, *, requester_id: uuid.UUID) -> None:
        document = await self.get(document_id, requester_id=requester_id)
        await self._repo.delete(document_id)
        # The API deletion is complete once its metadata is gone.  Storage is
        # best effort: a failure leaves an orphan and queues its retry rather
        # than turning a successful delete into an opaque client error.
        try:
            await self._storage.delete(document.storage_key)
        except Exception:
            logger.exception(
                "storage_delete_failed_queueing_cleanup", storage_key=document.storage_key
            )
            if self._enqueue_storage_cleanup is not None:
                try:
                    self._enqueue_storage_cleanup(document.storage_key)
                except Exception:
                    logger.exception(
                        "storage_cleanup_enqueue_failed", storage_key=document.storage_key
                    )

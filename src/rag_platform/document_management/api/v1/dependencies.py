"""FastAPI dependencies for the document_management API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.document_management.application.services.document_service import DocumentService
from rag_platform.document_management.infrastructure.repositories.postgres_document_repository import (  # noqa: E501
    PostgresDocumentRepository,
)
from rag_platform.document_management.infrastructure.storage.minio_object_storage import (
    MinioObjectStorage,
)
from rag_platform.document_management.tasks.process_document import enqueue_document_processing
from rag_platform.document_management.tasks.storage_cleanup import enqueue_storage_cleanup
from rag_platform.platform.database.dependencies import get_db_session


def get_document_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentService:
    container = request.app.state.container
    settings = request.app.state.settings
    return DocumentService(
        repository=PostgresDocumentRepository(session),
        storage=MinioObjectStorage(container.minio_client, settings.minio_bucket),
        max_size_bytes=settings.upload_max_size_bytes,
        allowed_content_types=settings.upload_allowed_content_types,
        presigned_expiry_seconds=settings.minio_presigned_expiry_seconds,
        enqueue_storage_cleanup=enqueue_storage_cleanup,
        # Full API tests use the real database transaction but do not need a
        # worker; task-specific tests exercise eager execution explicitly.
        enqueue_document_processing=(None if settings.is_testing else enqueue_document_processing),
    )

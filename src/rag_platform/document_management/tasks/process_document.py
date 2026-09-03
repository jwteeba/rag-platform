"""Celery task that turns an uploaded object into durable text chunks."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import rag_platform.identity_access.infrastructure.models  # noqa: F401
from rag_platform.core.celery import celery_app
from rag_platform.core.config import get_settings
from rag_platform.core.db import build_engine, build_session_factory
from rag_platform.core.logging import get_logger
from rag_platform.core.storage import build_minio_client
from rag_platform.document_management.application.services.chunking_service import ChunkingService
from rag_platform.document_management.application.services.text_extraction import extract_text
from rag_platform.document_management.domain.entities import DocumentStatus
from rag_platform.document_management.infrastructure.repositories.postgres_chunk_repository import (
    PostgresChunkRepository,
)
from rag_platform.document_management.infrastructure.repositories.postgres_document_repository import (  # noqa: E501
    PostgresDocumentRepository,
)
from rag_platform.document_management.infrastructure.storage.minio_object_storage import (
    MinioObjectStorage,
)

if TYPE_CHECKING:
    from celery import Task

logger = get_logger(__name__)


async def _process(document_id: uuid.UUID) -> int:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            documents = PostgresDocumentRepository(session)
            document = await documents.get_by_id(document_id)
            if document is None:
                # The uploader's request can still be committing when this
                # task begins. Raising lets Celery retry that short race.
                raise LookupError(f"document {document_id} is not committed yet")
            await documents.set_status(document_id, DocumentStatus.PROCESSING)
            await session.commit()

        storage = MinioObjectStorage(build_minio_client(settings), settings.minio_bucket)
        text = extract_text(
            data=await storage.read(document.storage_key), content_type=document.content_type
        )
        chunks = ChunkingService(
            chunk_size_tokens=settings.chunk_size_tokens,
            chunk_overlap_tokens=settings.chunk_overlap_tokens,
            max_chunks=settings.max_chunks_per_document,
        ).chunk(document_id=document_id, text=text)

        async with session_factory() as session:
            await PostgresChunkRepository(session).replace_for_document(document_id, chunks)
            await PostgresDocumentRepository(session).set_status(document_id, DocumentStatus.READY)
            await session.commit()
        logger.info(
            "document_processing_complete", document_id=str(document_id), chunk_count=len(chunks)
        )
        return len(chunks)
    finally:
        await engine.dispose()


async def _mark_failed(document_id: uuid.UUID) -> None:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            await PostgresDocumentRepository(session).set_status(document_id, DocumentStatus.FAILED)
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="document_management.process_document", max_retries=3)
def process_document(task: Task, document_id: str) -> int:
    """Extract and chunk one document; failures retry with bounded backoff."""
    parsed_document_id = uuid.UUID(document_id)
    try:
        return asyncio.run(_process(parsed_document_id))
    except Exception as exc:
        if task.request.retries >= task.max_retries:
            asyncio.run(_mark_failed(parsed_document_id))
            logger.exception("document_processing_failed", document_id=document_id)
            raise
        raise task.retry(exc=exc, countdown=2**task.request.retries) from exc


def enqueue_document_processing(document_id: uuid.UUID) -> None:
    process_document.delay(str(document_id))

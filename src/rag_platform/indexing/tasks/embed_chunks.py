"""Celery task that embeds document chunks and upserts them into Qdrant."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from qdrant_client.models import PointStruct

import rag_platform.identity_access.infrastructure.models  # noqa: F401
from rag_platform.core.celery import celery_app
from rag_platform.core.config import get_settings
from rag_platform.core.db import build_engine, build_session_factory
from rag_platform.core.logging import get_logger
from rag_platform.core.vector_store import build_qdrant_client
from rag_platform.document_management.domain.entities import EmbeddingStatus
from rag_platform.document_management.infrastructure.repositories.postgres_chunk_repository import (
    PostgresChunkRepository,
)
from rag_platform.document_management.infrastructure.repositories.postgres_document_repository import (  # noqa: E501
    PostgresDocumentRepository,
)

if TYPE_CHECKING:
    from celery import Task

logger = get_logger(__name__)


def _build_embedding_adapter(settings: object) -> object:
    """Instantiate the configured embedding adapter."""
    from rag_platform.core.config import Settings

    assert isinstance(settings, Settings)
    if settings.embedding_provider == "local":
        from rag_platform.indexing.infrastructure.embedding.sentence_transformer_adapter import (
            SentenceTransformerEmbeddingAdapter,
        )

        return SentenceTransformerEmbeddingAdapter(settings)
    from rag_platform.indexing.infrastructure.embedding.openai_adapter import (
        OpenAIEmbeddingAdapter,
    )

    return OpenAIEmbeddingAdapter(settings)


async def _embed(document_id: uuid.UUID) -> int:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            doc_repo = PostgresDocumentRepository(session)
            document = await doc_repo.get_by_id(document_id)
            if document is None:
                raise LookupError(f"document {document_id} not found")

            chunk_repo = PostgresChunkRepository(session)
            chunks = await chunk_repo.list_for_document(document_id)

        if not chunks:
            return 0

        adapter = _build_embedding_adapter(settings)
        texts = [c.content for c in chunks]
        vectors = adapter.embed(texts)  # type: ignore[attr-defined]

        qdrant = build_qdrant_client(settings)
        points = [
            PointStruct(
                id=str(chunk.id),
                vector=vector,
                payload={
                    "document_id": str(chunk.document_id),
                    "chunk_id": str(chunk.id),
                    "owner_id": str(document.owner_id),
                    "chunk_index": chunk.chunk_index,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        qdrant.upsert(collection_name=settings.qdrant_collection_name, points=points)

        # Mark chunks as indexed and record the Qdrant point id.
        for chunk, point in zip(chunks, points, strict=True):
            chunk.embedding_id = uuid.UUID(point.id)  # type: ignore[arg-type]
            chunk.embedding_status = EmbeddingStatus.INDEXED

        async with session_factory() as session:
            await PostgresChunkRepository(session).replace_for_document(document_id, chunks)
            await session.commit()

        logger.info(
            "embed_chunks_complete",
            document_id=str(document_id),
            chunk_count=len(chunks),
        )
        return len(chunks)
    finally:
        await engine.dispose()


async def _mark_chunks_failed(document_id: uuid.UUID) -> None:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            chunk_repo = PostgresChunkRepository(session)
            chunks = await chunk_repo.list_for_document(document_id)
            for chunk in chunks:
                chunk.embedding_status = EmbeddingStatus.FAILED
            await chunk_repo.replace_for_document(document_id, chunks)
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="indexing.embed_chunks", max_retries=3)
def embed_chunks(task: Task, document_id: str) -> int:
    """Embed all chunks for a document and upsert them into Qdrant."""
    parsed_id = uuid.UUID(document_id)
    try:
        return asyncio.run(_embed(parsed_id))
    except Exception as exc:
        if task.request.retries >= task.max_retries:
            asyncio.run(_mark_chunks_failed(parsed_id))
            logger.exception("embed_chunks_failed", document_id=document_id)
            raise
        raise task.retry(exc=exc, countdown=2**task.request.retries) from exc


def enqueue_embed_chunks(document_id: uuid.UUID) -> None:
    embed_chunks.delay(str(document_id))

"""FastAPI dependencies for the retrieval API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.indexing.domain.ports import EmbeddingPort
from rag_platform.indexing.infrastructure.cache.cached_embedding_adapter import (
    CachedEmbeddingAdapter,
)
from rag_platform.indexing.infrastructure.embedding.openai_adapter import OpenAIEmbeddingAdapter
from rag_platform.platform.database.dependencies import get_db_session
from rag_platform.retrieval.application.services.retrieval_service import RetrievalService
from rag_platform.retrieval.infrastructure.cache.cached_vector_search import CachedVectorSearch
from rag_platform.retrieval.infrastructure.repositories.postgres_chunk_metadata_repository import (
    PostgresChunkMetadataRepository,
)
from rag_platform.retrieval.infrastructure.vector_search.qdrant_vector_search import (
    QdrantVectorSearch,
)


def get_retrieval_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RetrievalService:
    container = request.app.state.container
    settings = request.app.state.settings

    embedding_port: EmbeddingPort

    base_embedding: EmbeddingPort
    if settings.embedding_provider == "local":
        from rag_platform.indexing.infrastructure.embedding.sentence_transformer_adapter import (
            SentenceTransformerEmbeddingAdapter,
        )

        base_embedding = SentenceTransformerEmbeddingAdapter(settings)
    else:
        base_embedding = OpenAIEmbeddingAdapter(settings)
    embedding_port = CachedEmbeddingAdapter(
        base_embedding,
        container.cache_sync_client,
        model=f"{settings.embedding_provider}:{settings.embedding_model}",
        ttl_seconds=settings.embedding_cache_ttl_seconds,
        enabled=settings.embedding_cache_enabled,
    )

    return RetrievalService(
        embedding_port=embedding_port,
        vector_search=CachedVectorSearch(
            QdrantVectorSearch(container.qdrant_client, settings),
            container.cache_sync_client,
            ttl_seconds=settings.retrieval_cache_ttl_seconds,
            enabled=settings.retrieval_cache_enabled,
        ),
        chunk_repo=PostgresChunkMetadataRepository(session),
        score_threshold=settings.search_score_threshold,
        limit_max=settings.search_result_limit_max,
    )

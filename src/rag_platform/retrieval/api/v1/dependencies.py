"""FastAPI dependencies for the retrieval API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.indexing.domain.ports import EmbeddingPort
from rag_platform.indexing.infrastructure.embedding.openai_adapter import OpenAIEmbeddingAdapter
from rag_platform.indexing.infrastructure.embedding.sentence_transformer_adapter import (
    SentenceTransformerEmbeddingAdapter,
)
from rag_platform.platform.database.dependencies import get_db_session
from rag_platform.retrieval.application.services.retrieval_service import RetrievalService
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

    if settings.embedding_provider == "local":
        embedding_port = SentenceTransformerEmbeddingAdapter(settings)
    else:
        embedding_port = OpenAIEmbeddingAdapter(settings)

    return RetrievalService(
        embedding_port=embedding_port,
        vector_search=QdrantVectorSearch(container.qdrant_client, settings),
        chunk_repo=PostgresChunkMetadataRepository(session),
        score_threshold=settings.search_score_threshold,
        limit_max=settings.search_result_limit_max,
    )

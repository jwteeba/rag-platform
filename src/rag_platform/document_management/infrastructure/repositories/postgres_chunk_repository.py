"""Postgres-backed storage for processed document chunks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from rag_platform.document_management.domain.entities import Chunk, EmbeddingStatus
from rag_platform.document_management.domain.ports import ChunkRepositoryPort
from rag_platform.document_management.infrastructure.models import ChunkModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: ChunkModel) -> Chunk:
    return Chunk(
        id=model.id,
        document_id=model.document_id,
        content=model.content,
        chunk_index=model.chunk_index,
        token_count=model.token_count,
        embedding_id=model.embedding_id,
        embedding_status=EmbeddingStatus(model.embedding_status),
    )


class PostgresChunkRepository(ChunkRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_for_document(self, document_id: uuid.UUID, chunks: list[Chunk]) -> None:
        """Replace all chunks atomically, making task retries idempotent."""
        await self._session.execute(delete(ChunkModel).where(ChunkModel.document_id == document_id))
        self._session.add_all(
            [
                ChunkModel(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                    embedding_id=chunk.embedding_id,
                    embedding_status=chunk.embedding_status.value,
                )
                for chunk in chunks
            ]
        )
        await self._session.flush()

    async def list_for_document(self, document_id: uuid.UUID) -> list[Chunk]:
        result = await self._session.execute(
            select(ChunkModel)
            .where(ChunkModel.document_id == document_id)
            .order_by(ChunkModel.chunk_index)
        )
        return [_to_domain(model) for model in result.scalars().all()]

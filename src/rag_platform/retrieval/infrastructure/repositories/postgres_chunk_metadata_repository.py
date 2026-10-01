"""Postgres implementation of ChunkMetadataRepositoryPort."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from rag_platform.document_management.infrastructure.models import ChunkModel, DocumentModel
from rag_platform.retrieval.domain.entities import SearchResult

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class PostgresChunkMetadataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_chunks_with_filename(self, chunk_ids: list[uuid.UUID]) -> list[SearchResult]:
        if not chunk_ids:
            return []

        result = await self._session.execute(
            select(ChunkModel, DocumentModel.filename)
            .join(DocumentModel, ChunkModel.document_id == DocumentModel.id)
            .where(ChunkModel.id.in_(chunk_ids))
        )
        rows = result.all()

        # Preserve Qdrant ranking order.
        order = {cid: i for i, cid in enumerate(chunk_ids)}
        hydrated = [
            SearchResult(
                chunk_id=row.ChunkModel.id,
                document_id=row.ChunkModel.document_id,
                filename=row.filename,
                content=row.ChunkModel.content,
                score=0.0,  # filled in by RetrievalService
                chunk_index=row.ChunkModel.chunk_index,
            )
            for row in rows
        ]
        hydrated.sort(key=lambda r: order.get(r.chunk_id, len(chunk_ids)))
        return hydrated

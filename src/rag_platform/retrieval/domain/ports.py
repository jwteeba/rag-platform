"""Retrieval domain ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid

    from rag_platform.retrieval.domain.entities import SearchResult


@runtime_checkable
class VectorSearchPort(Protocol):
    def search(
        self,
        query_vector: list[float],
        owner_id: uuid.UUID,
        *,
        limit: int,
        score_threshold: float,
        document_ids: list[uuid.UUID] | None,
    ) -> list[tuple[uuid.UUID, float]]:
        """Return (chunk_id, score) pairs, filtered by owner_id."""
        ...


@runtime_checkable
class ChunkMetadataRepositoryPort(Protocol):
    async def get_chunks_with_filename(self, chunk_ids: list[uuid.UUID]) -> list[SearchResult]:
        """Hydrate chunk_ids into SearchResult objects (with document filename)."""
        ...

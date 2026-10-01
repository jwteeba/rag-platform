"""RetrievalService: embed query → vector search → hydrate → return ranked results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_platform.retrieval.domain.exceptions import InvalidQueryError, NoResultsFoundError

if TYPE_CHECKING:
    import uuid

    from rag_platform.indexing.domain.ports import EmbeddingPort
    from rag_platform.retrieval.domain.entities import SearchResult
    from rag_platform.retrieval.domain.ports import ChunkMetadataRepositoryPort, VectorSearchPort


class RetrievalService:
    def __init__(
        self,
        embedding_port: EmbeddingPort,
        vector_search: VectorSearchPort,
        chunk_repo: ChunkMetadataRepositoryPort,
        score_threshold: float,
        limit_max: int,
    ) -> None:
        self._embedding_port = embedding_port
        self._vector_search = vector_search
        self._chunk_repo = chunk_repo
        self._score_threshold = score_threshold
        self._limit_max = limit_max

    async def search(
        self,
        query: str,
        owner_id: uuid.UUID,
        *,
        limit: int,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise InvalidQueryError("Query must not be empty.")

        limit = min(limit, self._limit_max)

        vectors = self._embedding_port.embed([query])
        hits = self._vector_search.search(
            vectors[0],
            owner_id,
            limit=limit,
            score_threshold=self._score_threshold,
            document_ids=document_ids,
        )

        if not hits:
            raise NoResultsFoundError()

        chunk_ids = [chunk_id for chunk_id, _ in hits]
        scores = dict(hits)

        results = await self._chunk_repo.get_chunks_with_filename(chunk_ids)
        for result in results:
            result.score = scores.get(result.chunk_id, 0.0)

        return results

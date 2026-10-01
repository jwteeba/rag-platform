"""Qdrant implementation of VectorSearchPort."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdrant_client.models import Condition, FieldCondition, Filter, MatchAny, MatchValue

if TYPE_CHECKING:
    import uuid

    from qdrant_client import QdrantClient

    from rag_platform.core.config import Settings


class QdrantVectorSearch:
    """Implements VectorSearchPort against a Qdrant collection.

    Every query is filtered by `owner_id` so users can never retrieve
    chunks from documents they don't own — even if they supply a known
    document_id. The filter is applied inside Qdrant (not post-filter)
    so the `limit` is honoured correctly. See ADR-0013.
    """

    def __init__(self, client: QdrantClient, settings: Settings) -> None:
        self._client = client
        self._collection = settings.qdrant_collection_name

    def search(
        self,
        query_vector: list[float],
        owner_id: uuid.UUID,
        *,
        limit: int,
        score_threshold: float,
        document_ids: list[uuid.UUID] | None,
    ) -> list[tuple[uuid.UUID, float]]:
        import uuid as _uuid

        conditions: list[Condition] = [
            FieldCondition(
                key="owner_id",
                match=MatchValue(value=str(owner_id)),
            )
        ]

        if document_ids:
            conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any=[str(did) for did in document_ids]),
                )
            )

        results = self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            query_filter=Filter(must=conditions),
            limit=limit,
            score_threshold=score_threshold,
        )

        output: list[tuple[uuid.UUID, float]] = []

        for result in results:
            if result.payload is None or "chunk_id" not in result.payload:
                raise ValueError("Qdrant result is missing required chunk_id payload")

            output.append((_uuid.UUID(str(result.payload["chunk_id"])), result.score))

        return output

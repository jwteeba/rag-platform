"""Owner-scoped Redis cache around vector search results."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import TYPE_CHECKING, cast

from rag_platform.core.cache import log_cache_access

if TYPE_CHECKING:
    from redis import Redis

    from rag_platform.retrieval.domain.ports import VectorSearchPort


class CachedVectorSearch:
    def __init__(
        self,
        wrapped: VectorSearchPort,
        client: Redis,
        *,
        ttl_seconds: int,
        enabled: bool = True,
    ) -> None:
        self._wrapped = wrapped
        self._client = client
        self._ttl = ttl_seconds
        self._enabled = enabled

    @staticmethod
    def _key(
        query_vector: list[float],
        owner_id: uuid.UUID,
        *,
        limit: int,
        score_threshold: float,
        document_ids: list[uuid.UUID] | None,
    ) -> str:
        vector_digest = hashlib.sha256(
            json.dumps(query_vector, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        filters = sorted(str(value) for value in document_ids or [])
        filter_digest = hashlib.sha256(json.dumps(filters).encode()).hexdigest()[:16]
        threshold = format(score_threshold, ".8g")
        return f"rag:cache:retrieval:{owner_id}:{vector_digest}:{limit}:{threshold}:{filter_digest}"

    def search(
        self,
        query_vector: list[float],
        owner_id: uuid.UUID,
        *,
        limit: int,
        score_threshold: float,
        document_ids: list[uuid.UUID] | None,
    ) -> list[tuple[uuid.UUID, float]]:
        if not self._enabled:
            return self._wrapped.search(
                query_vector,
                owner_id,
                limit=limit,
                score_threshold=score_threshold,
                document_ids=document_ids,
            )

        key = self._key(
            query_vector,
            owner_id,
            limit=limit,
            score_threshold=score_threshold,
            document_ids=document_ids,
        )
        started_at = time.perf_counter()
        try:
            raw = self._client.get(key)
            hit = raw is not None
            log_cache_access(self._client, layer="retrieval", hit=hit, started_at=started_at)
            if hit:
                return [
                    (uuid.UUID(chunk_id), float(score))
                    for chunk_id, score in json.loads(cast(str, raw))
                ]
        except Exception:
            log_cache_access(self._client, layer="retrieval", hit=False, started_at=started_at)

        results = self._wrapped.search(
            query_vector,
            owner_id,
            limit=limit,
            score_threshold=score_threshold,
            document_ids=document_ids,
        )
        try:
            value = [[str(chunk_id), score] for chunk_id, score in results]
            self._client.set(key, json.dumps(value), ex=self._ttl)
        except Exception:
            pass
        return results

"""Content-addressed Redis cache around any embedding provider."""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, cast

from rag_platform.core.cache import log_cache_access

if TYPE_CHECKING:
    from redis import Redis

    from rag_platform.indexing.domain.ports import EmbeddingPort


class CachedEmbeddingAdapter:
    """Cache embeddings by provider model and exact text digest.

    Redis errors fail open: the wrapped embedding provider remains the source
    of truth and is called directly when the cache cannot be read or written.
    """

    def __init__(
        self,
        wrapped: EmbeddingPort,
        client: Redis,
        *,
        model: str,
        ttl_seconds: int,
        enabled: bool = True,
    ) -> None:
        self._wrapped = wrapped
        self._client = client
        self._model = model
        self._ttl = ttl_seconds
        self._enabled = enabled

    def _key(self, text: str) -> str:
        model_hash = hashlib.sha256(self._model.encode()).hexdigest()[:16]
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"rag:cache:embedding:{model_hash}:{text_hash}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._enabled:
            return self._wrapped.embed(texts)

        values: list[list[float] | None] = [None] * len(texts)
        missing_by_key: dict[str, str] = {}
        try:
            for index, text in enumerate(texts):
                key = self._key(text)
                started_at = time.perf_counter()
                raw = self._client.get(key)
                hit = raw is not None
                log_cache_access(self._client, layer="embedding", hit=hit, started_at=started_at)
                if hit:
                    values[index] = json.loads(cast(str, raw))
                else:
                    missing_by_key[key] = text
        except Exception:
            log_cache_access(
                self._client,
                layer="embedding",
                hit=False,
                started_at=time.perf_counter(),
            )
            return self._wrapped.embed(texts)

        if missing_by_key:
            missing_texts = list(missing_by_key.values())
            generated = self._wrapped.embed(missing_texts)
            by_key = dict(zip(missing_by_key, generated, strict=True))
            try:
                pipeline = self._client.pipeline()
                for key, vector in by_key.items():
                    pipeline.set(key, json.dumps(vector), ex=self._ttl)
                pipeline.execute()
            except Exception:
                pass

            for index, text in enumerate(texts):
                key = self._key(text)
                if values[index] is None:
                    values[index] = by_key[key]

        return [vector for vector in values if vector is not None]

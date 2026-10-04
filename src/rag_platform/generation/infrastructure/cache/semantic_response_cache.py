"""High-threshold owner-scoped semantic cache for completed answers."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

from rag_platform.core.cache import log_cache_access
from rag_platform.generation.domain.entities import GenerationResult

if TYPE_CHECKING:
    from redis import Redis


class SemanticResponseCache:
    """Search recent Redis-stored query vectors for a similar answer.

    Entries are isolated by owner and runtime namespace (provider/model and
    generation settings). A bounded scan keeps this deliberately small and
    TTL owns expiry; false-positive matches remain a documented tradeoff.
    """

    _MAX_CANDIDATES = 500

    def __init__(self, client: Redis, *, ttl_seconds: int, enabled: bool = True) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._enabled = enabled

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _namespace_key(namespace: str) -> str:
        return hashlib.sha256(namespace.encode()).hexdigest()[:16]

    def lookup(
        self,
        owner_id: uuid.UUID,
        query_vector: list[float],
        *,
        namespace: str,
        similarity_threshold: float,
    ) -> GenerationResult | None:
        if not self._enabled:
            return None
        prefix = f"rag:cache:llm:{owner_id}:{self._namespace_key(namespace)}:"
        started_at = time.perf_counter()
        best_score = -1.0
        best_result: GenerationResult | None = None
        try:
            seen = 0
            for key in self._client.scan_iter(match=f"{prefix}*", count=100):
                if seen >= self._MAX_CANDIDATES:
                    break
                seen += 1
                raw = self._client.get(key)
                if raw is None:
                    continue
                record: dict[str, Any] = json.loads(cast(str, raw))
                score = self._cosine(query_vector, record["query_vector"])
                if score >= similarity_threshold and score > best_score:
                    best_score = score
                    best_result = GenerationResult(
                        answer=record["answer"],
                        source_documents=record["source_documents"],
                        prompt_tokens=record["prompt_tokens"],
                        completion_tokens=record["completion_tokens"],
                        total_tokens=record["total_tokens"],
                    )
            log_cache_access(
                self._client,
                layer="llm",
                hit=best_result is not None,
                started_at=started_at,
            )
            return best_result
        except Exception:
            log_cache_access(self._client, layer="llm", hit=False, started_at=started_at)
            return None

    def store(
        self,
        owner_id: uuid.UUID,
        query_vector: list[float],
        result: GenerationResult,
        *,
        namespace: str,
    ) -> None:
        if not self._enabled:
            return
        key = f"rag:cache:llm:{owner_id}:{self._namespace_key(namespace)}:{uuid.uuid4()}"
        value = {
            "query_vector": query_vector,
            "answer": result.answer,
            "source_documents": result.source_documents,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
        }
        with suppress(Exception):
            self._client.set(key, json.dumps(value), ex=self._ttl)

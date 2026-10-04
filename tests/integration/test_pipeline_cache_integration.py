from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

import pytest
from redis import Redis

from rag_platform.generation.domain.entities import GenerationResult
from rag_platform.generation.infrastructure.cache.semantic_response_cache import (
    SemanticResponseCache,
)
from rag_platform.indexing.infrastructure.cache.cached_embedding_adapter import (
    CachedEmbeddingAdapter,
)
from rag_platform.retrieval.infrastructure.cache.cached_vector_search import CachedVectorSearch
from tests.conftest import TEST_REDIS_URL


class CountingEmbedding:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(len(text)), 1.0] for text in texts]


class CountingVectorSearch:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query_vector, owner_id, *, limit, score_threshold, document_ids):
        self.calls += 1
        return [(uuid.UUID(int=7), 0.8)]


@pytest.fixture
async def redis_sync(clean_cache: None) -> AsyncIterator[Redis]:
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    client.close()


@pytest.mark.asyncio
async def test_embedding_cache_hit_and_ttl_expiry(redis_sync: Redis) -> None:
    base = CountingEmbedding()
    cache = CachedEmbeddingAdapter(base, redis_sync, model="integration-model", ttl_seconds=1)

    first = cache.embed(["same text"])
    assert cache.embed(["same text"]) == first
    assert base.calls == 1

    time.sleep(1.1)
    cache.embed(["same text"])
    assert base.calls == 2


@pytest.mark.asyncio
async def test_retrieval_cache_hits_are_isolated_by_owner(redis_sync: Redis) -> None:
    base = CountingVectorSearch()
    cache = CachedVectorSearch(base, redis_sync, ttl_seconds=30)
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
    first = cache.search([0.1, 0.2], owner_a, limit=3, score_threshold=0.7, document_ids=None)
    assert (
        cache.search([0.1, 0.2], owner_a, limit=3, score_threshold=0.7, document_ids=None) == first
    )
    cache.search([0.1, 0.2], owner_b, limit=3, score_threshold=0.7, document_ids=None)
    assert base.calls == 2


@pytest.mark.asyncio
async def test_semantic_response_cache_hit_has_same_generation_result(redis_sync: Redis) -> None:
    owner = uuid.uuid4()
    cache = SemanticResponseCache(redis_sync, ttl_seconds=30)
    result = GenerationResult("stable answer", [], 8, 3, 11)
    cache.store(owner, [1.0, 0.0], result, namespace="provider:model")

    cached = cache.lookup(
        owner,
        [0.999, 0.01],
        namespace="provider:model",
        similarity_threshold=0.97,
    )
    assert cached == result

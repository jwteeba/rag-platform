from __future__ import annotations

import uuid
from typing import cast

import fakeredis

from rag_platform.generation.domain.entities import GenerationResult
from rag_platform.generation.infrastructure.cache.semantic_response_cache import (
    SemanticResponseCache,
)
from rag_platform.indexing.infrastructure.cache.cached_embedding_adapter import (
    CachedEmbeddingAdapter,
)
from rag_platform.retrieval.infrastructure.cache.cached_vector_search import CachedVectorSearch


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(len(text)), 1.0] for text in texts]


class FakeVectorSearch:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query_vector, owner_id, *, limit, score_threshold, document_ids):
        self.calls += 1
        return [(uuid.UUID(int=5), 0.9)]


def test_embedding_cache_is_content_and_model_addressed() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    base = FakeEmbedding()
    cache = CachedEmbeddingAdapter(base, client, model="model-a", ttl_seconds=60)

    first = cache.embed(["repeat", "other"])
    second = cache.embed(["repeat"])
    other_model = CachedEmbeddingAdapter(base, client, model="model-b", ttl_seconds=60)
    third = other_model.embed(["repeat"])

    assert first[0] == second[0]
    assert third == first[:1]
    assert base.calls == 2
    assert cast(int, client.ttl(next(iter(client.scan_iter(match="rag:cache:embedding:*"))))) > 0


def test_retrieval_cache_is_owner_and_filter_scoped() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    base = FakeVectorSearch()
    cache = CachedVectorSearch(base, client, ttl_seconds=60)
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()

    a_result = cache.search([0.1, 0.2], owner_a, limit=4, score_threshold=0.7, document_ids=None)
    assert (
        cache.search([0.1, 0.2], owner_a, limit=4, score_threshold=0.7, document_ids=None)
        == a_result
    )
    cache.search([0.1, 0.2], owner_b, limit=4, score_threshold=0.7, document_ids=None)

    assert base.calls == 2
    assert client.get("rag:cache:metrics:retrieval:hits") == "1"


def test_semantic_response_cache_returns_only_high_similarity_results() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    cache = SemanticResponseCache(client, ttl_seconds=60)
    owner = uuid.uuid4()
    result = GenerationResult("answer", [{"filename": "doc.pdf", "chunk_index": 1}], 5, 2, 7)
    cache.store(owner, [1.0, 0.0], result, namespace="openai:gpt-4o")

    hit = cache.lookup(
        owner,
        [0.999, 0.01],
        namespace="openai:gpt-4o",
        similarity_threshold=0.97,
    )
    miss = cache.lookup(
        owner,
        [0.0, 1.0],
        namespace="openai:gpt-4o",
        similarity_threshold=0.97,
    )
    other_owner = cache.lookup(
        uuid.uuid4(),
        [1.0, 0.0],
        namespace="openai:gpt-4o",
        similarity_threshold=0.97,
    )

    assert hit == result
    assert miss is None
    assert other_owner is None

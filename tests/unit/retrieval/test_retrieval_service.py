"""Unit tests for RetrievalService using fakes for both ports."""

from __future__ import annotations

import uuid

import pytest

from rag_platform.retrieval.application.services.retrieval_service import RetrievalService
from rag_platform.retrieval.domain.entities import SearchResult
from rag_platform.retrieval.domain.exceptions import InvalidQueryError, NoResultsFoundError


class FakeEmbeddingPort:
    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector or [0.1, 0.2, 0.3, 0.4]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


class FakeVectorSearch:
    def __init__(self, hits: list[tuple[uuid.UUID, float]] | None = None) -> None:
        self._hits = hits or []
        self.last_call: dict = {}

    def search(
        self,
        query_vector: list[float],
        owner_id: uuid.UUID,
        *,
        limit: int,
        score_threshold: float,
        document_ids: list[uuid.UUID] | None,
    ) -> list[tuple[uuid.UUID, float]]:
        self.last_call = {
            "owner_id": owner_id,
            "limit": limit,
            "score_threshold": score_threshold,
            "document_ids": document_ids,
        }
        return self._hits


class FakeChunkRepo:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or []

    async def get_chunks_with_filename(self, chunk_ids: list[uuid.UUID]) -> list[SearchResult]:
        return [r for r in self._results if r.chunk_id in chunk_ids]


def _make_result(chunk_id: uuid.UUID, doc_id: uuid.UUID) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        document_id=doc_id,
        filename="doc.pdf",
        content="some content",
        score=0.0,
        chunk_index=0,
    )


def _service(
    hits: list[tuple[uuid.UUID, float]] | None = None,
    results: list[SearchResult] | None = None,
    score_threshold: float = 0.7,
    limit_max: int = 20,
) -> tuple[RetrievalService, FakeVectorSearch]:
    vector_search = FakeVectorSearch(hits)
    chunk_repo = FakeChunkRepo(results)
    svc = RetrievalService(
        embedding_port=FakeEmbeddingPort(),
        vector_search=vector_search,
        chunk_repo=chunk_repo,
        score_threshold=score_threshold,
        limit_max=limit_max,
    )
    return svc, vector_search


@pytest.mark.asyncio
async def test_empty_query_raises_invalid_query_error() -> None:
    svc, _ = _service()
    with pytest.raises(InvalidQueryError):
        await svc.search("   ", uuid.uuid4(), limit=5)


@pytest.mark.asyncio
async def test_no_hits_raises_no_results_found() -> None:
    svc, _ = _service(hits=[])
    with pytest.raises(NoResultsFoundError):
        await svc.search("what is RAG?", uuid.uuid4(), limit=5)


@pytest.mark.asyncio
async def test_returns_ranked_results_with_scores() -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    result = _make_result(chunk_id, doc_id)

    svc, _ = _service(hits=[(chunk_id, 0.92)], results=[result])
    found = await svc.search("query", owner_id, limit=5)

    assert len(found) == 1
    assert found[0].chunk_id == chunk_id
    assert found[0].score == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_limit_capped_at_limit_max() -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    result = _make_result(chunk_id, doc_id)

    svc, vector_search = _service(hits=[(chunk_id, 0.9)], results=[result], limit_max=10)
    await svc.search("query", owner_id, limit=50)

    assert vector_search.last_call["limit"] == 10


@pytest.mark.asyncio
async def test_owner_id_forwarded_to_vector_search() -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    result = _make_result(chunk_id, doc_id)

    svc, vector_search = _service(hits=[(chunk_id, 0.9)], results=[result])
    await svc.search("query", owner_id, limit=5)

    assert vector_search.last_call["owner_id"] == owner_id


@pytest.mark.asyncio
async def test_document_ids_filter_forwarded() -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    result = _make_result(chunk_id, doc_id)

    svc, vector_search = _service(hits=[(chunk_id, 0.9)], results=[result])
    await svc.search("query", owner_id, limit=5, document_ids=[doc_id])

    assert vector_search.last_call["document_ids"] == [doc_id]


@pytest.mark.asyncio
async def test_score_threshold_forwarded() -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    result = _make_result(chunk_id, doc_id)

    svc, vector_search = _service(hits=[(chunk_id, 0.9)], results=[result], score_threshold=0.5)
    await svc.search("query", owner_id, limit=5)

    assert vector_search.last_call["score_threshold"] == pytest.approx(0.5)

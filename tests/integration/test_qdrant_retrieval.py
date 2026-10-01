"""Integration tests for QdrantVectorSearch against an in-memory Qdrant instance."""

from __future__ import annotations

import uuid

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from rag_platform.core.config import Settings
from rag_platform.core.vector_store import ensure_collection_exists
from rag_platform.retrieval.infrastructure.vector_search.qdrant_vector_search import (
    QdrantVectorSearch,
)

TEST_COLLECTION = "retrieval_test"
DIM = 4


@pytest.fixture
def qdrant_settings() -> Settings:
    return Settings(
        qdrant_collection_name=TEST_COLLECTION,
        embedding_dimensions=DIM,
        openai_api_key=None,
        qdrant_api_key=None,
        qdrant_https=False,
        search_score_threshold=0.0,
        search_result_limit_max=20,
    )


@pytest.fixture
def qdrant_client(qdrant_settings: Settings) -> QdrantClient:
    client = QdrantClient(":memory:")
    existing = {c.name for c in client.get_collections().collections}
    if TEST_COLLECTION in existing:
        client.delete_collection(TEST_COLLECTION)
    ensure_collection_exists(client, qdrant_settings)
    return client


def _seed(
    client: QdrantClient,
    *,
    chunk_id: uuid.UUID,
    doc_id: uuid.UUID,
    owner_id: uuid.UUID,
    vector: list[float],
    chunk_index: int = 0,
) -> None:
    client.upsert(
        collection_name=TEST_COLLECTION,
        points=[
            PointStruct(
                id=str(chunk_id),
                vector=vector,
                payload={
                    "chunk_id": str(chunk_id),
                    "document_id": str(doc_id),
                    "owner_id": str(owner_id),
                    "chunk_index": chunk_index,
                },
            )
        ],
    )


def test_search_returns_matching_chunk(
    qdrant_client: QdrantClient, qdrant_settings: Settings
) -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    vector = [1.0, 0.0, 0.0, 0.0]
    _seed(qdrant_client, chunk_id=chunk_id, doc_id=doc_id, owner_id=owner_id, vector=vector)

    searcher = QdrantVectorSearch(qdrant_client, qdrant_settings)
    results = searcher.search(vector, owner_id, limit=5, score_threshold=0.0, document_ids=None)

    assert len(results) == 1
    assert results[0][0] == chunk_id
    assert results[0][1] > 0.99


def test_search_enforces_owner_isolation(
    qdrant_client: QdrantClient, qdrant_settings: Settings
) -> None:
    alice_id = uuid.uuid4()
    bob_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    vector = [1.0, 0.0, 0.0, 0.0]
    _seed(qdrant_client, chunk_id=chunk_id, doc_id=doc_id, owner_id=alice_id, vector=vector)

    searcher = QdrantVectorSearch(qdrant_client, qdrant_settings)
    results = searcher.search(vector, bob_id, limit=5, score_threshold=0.0, document_ids=None)

    assert results == []


def test_search_filters_by_document_ids(
    qdrant_client: QdrantClient, qdrant_settings: Settings
) -> None:
    owner_id = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    chunk_a = uuid.uuid4()
    chunk_b = uuid.uuid4()
    vector = [1.0, 0.0, 0.0, 0.0]
    _seed(qdrant_client, chunk_id=chunk_a, doc_id=doc_a, owner_id=owner_id, vector=vector)
    _seed(qdrant_client, chunk_id=chunk_b, doc_id=doc_b, owner_id=owner_id, vector=vector)

    searcher = QdrantVectorSearch(qdrant_client, qdrant_settings)
    results = searcher.search(vector, owner_id, limit=5, score_threshold=0.0, document_ids=[doc_a])

    returned_ids = {r[0] for r in results}
    assert chunk_a in returned_ids
    assert chunk_b not in returned_ids


def test_search_respects_score_threshold(
    qdrant_client: QdrantClient, qdrant_settings: Settings
) -> None:
    owner_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    # Orthogonal vector → cosine similarity ≈ 0 with query [1,0,0,0]
    _seed(
        qdrant_client,
        chunk_id=chunk_id,
        doc_id=doc_id,
        owner_id=owner_id,
        vector=[0.0, 1.0, 0.0, 0.0],
    )

    searcher = QdrantVectorSearch(qdrant_client, qdrant_settings)
    results = searcher.search(
        [1.0, 0.0, 0.0, 0.0], owner_id, limit=5, score_threshold=0.99, document_ids=None
    )

    assert results == []

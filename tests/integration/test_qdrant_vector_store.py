"""Integration tests for Qdrant vector store.

Requires a real Qdrant instance. `make test` starts Docker Compose's qdrant
service; direct `pytest` runs fall back to localhost:6333.
"""

from __future__ import annotations

import os
import uuid

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from rag_platform.core.config import Settings
from rag_platform.core.vector_store import ensure_collection_exists

TEST_QDRANT_HOST = os.getenv("APP_TEST_QDRANT_HOST", "localhost")
TEST_QDRANT_PORT = int(os.getenv("APP_TEST_QDRANT_PORT", "6333"))
TEST_COLLECTION = "rag_platform_test"


@pytest.fixture
def qdrant_client() -> QdrantClient:
    client = QdrantClient(host=TEST_QDRANT_HOST, port=TEST_QDRANT_PORT)
    # Clean up any leftover collection from a previous run.
    existing = {c.name for c in client.get_collections().collections}
    if TEST_COLLECTION in existing:
        client.delete_collection(TEST_COLLECTION)
    return client


@pytest.fixture
def test_settings_qdrant() -> Settings:
    return Settings(
        qdrant_host=TEST_QDRANT_HOST,
        qdrant_port=TEST_QDRANT_PORT,
        qdrant_collection_name=TEST_COLLECTION,
        embedding_dimensions=4,
        openai_api_key=None,
    )


def test_ensure_collection_creates_collection(
    qdrant_client: QdrantClient, test_settings_qdrant: Settings
) -> None:
    ensure_collection_exists(qdrant_client, test_settings_qdrant)

    names = {c.name for c in qdrant_client.get_collections().collections}
    assert TEST_COLLECTION in names


def test_ensure_collection_is_idempotent(
    qdrant_client: QdrantClient, test_settings_qdrant: Settings
) -> None:
    ensure_collection_exists(qdrant_client, test_settings_qdrant)
    ensure_collection_exists(qdrant_client, test_settings_qdrant)  # must not raise

    names = {c.name for c in qdrant_client.get_collections().collections}
    assert TEST_COLLECTION in names


def test_upsert_and_query_points(
    qdrant_client: QdrantClient, test_settings_qdrant: Settings
) -> None:
    ensure_collection_exists(qdrant_client, test_settings_qdrant)

    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    vector = [0.1, 0.2, 0.3, 0.4]

    qdrant_client.upsert(
        collection_name=TEST_COLLECTION,
        points=[
            PointStruct(
                id=str(chunk_id),
                vector=vector,
                payload={
                    "document_id": str(doc_id),
                    "chunk_id": str(chunk_id),
                    "owner_id": str(owner_id),
                    "chunk_index": 0,
                },
            )
        ],
    )

    results = qdrant_client.search(
        collection_name=TEST_COLLECTION,
        query_vector=vector,
        limit=1,
    )

    assert len(results) == 1
    assert results[0].payload["chunk_id"] == str(chunk_id)
    assert results[0].payload["owner_id"] == str(owner_id)
    assert results[0].payload["document_id"] == str(doc_id)

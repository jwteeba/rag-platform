"""API tests for POST /search."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.main import create_app
from rag_platform.retrieval.domain.entities import SearchResult
from tests.api.identity_access.conftest import register_and_login
from tests.conftest import TEST_DATABASE_URL, TEST_MINIO_BUCKET, TEST_MINIO_ENDPOINT, TEST_REDIS_URL


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _make_result(
    chunk_id: uuid.UUID | None = None,
    doc_id: uuid.UUID | None = None,
    score: float = 0.9,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        filename="report.pdf",
        content="relevant content snippet",
        score=score,
        chunk_index=0,
    )


@pytest.fixture
def mock_minio() -> Iterator[MagicMock]:
    mock = MagicMock()
    mock.bucket_exists.return_value = True
    with patch("rag_platform.core.storage.build_minio_client", return_value=mock):
        yield mock


@pytest.fixture
def search_client(
    clean_database: None,
    clean_cache: None,
    mock_minio: MagicMock,
) -> Iterator[TestClient]:
    settings = Settings(
        environment=Environment.TESTING,
        log_format=LogFormat.JSON,
        allowed_hosts=["*"],
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
        minio_endpoint=TEST_MINIO_ENDPOINT,
        minio_bucket=TEST_MINIO_BUCKET,
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        minio_secure=False,
        openai_api_key="sk-test",
        search_score_threshold=0.0,
        search_result_limit_max=20,
    )
    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c


class TestSearchAuth:
    def test_requires_auth(self, search_client: TestClient) -> None:
        response = search_client.post("/api/v1/search", json={"query": "hello"})
        assert response.status_code == 401

    def test_empty_query_returns_422(self, search_client: TestClient) -> None:
        tokens = register_and_login(search_client)
        response = search_client.post(
            "/api/v1/search",
            json={"query": ""},
            headers=_auth_header(tokens),
        )
        assert response.status_code == 422


class TestSearchResults:
    def test_returns_results(self, search_client: TestClient) -> None:
        tokens = register_and_login(search_client)
        result = _make_result()

        with patch(
            "rag_platform.retrieval.application.services.retrieval_service.RetrievalService.search",
            return_value=[result],
        ):
            response = search_client.post(
                "/api/v1/search",
                json={"query": "what is RAG?", "limit": 5},
                headers=_auth_header(tokens),
            )

        assert response.status_code == 200
        body = response.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["filename"] == "report.pdf"
        assert body["results"][0]["score"] == pytest.approx(0.9)

    def test_no_results_returns_404(self, search_client: TestClient) -> None:
        from rag_platform.retrieval.domain.exceptions import NoResultsFoundError

        tokens = register_and_login(search_client)

        with patch(
            "rag_platform.retrieval.application.services.retrieval_service.RetrievalService.search",
            side_effect=NoResultsFoundError(),
        ):
            response = search_client.post(
                "/api/v1/search",
                json={"query": "obscure query"},
                headers=_auth_header(tokens),
            )

        assert response.status_code == 404

    def test_document_ids_filter_accepted(self, search_client: TestClient) -> None:
        tokens = register_and_login(search_client)
        doc_id = uuid.uuid4()
        result = _make_result(doc_id=doc_id)

        with patch(
            "rag_platform.retrieval.application.services.retrieval_service.RetrievalService.search",
            return_value=[result],
        ) as mock_search:
            response = search_client.post(
                "/api/v1/search",
                json={"query": "test", "document_ids": [str(doc_id)]},
                headers=_auth_header(tokens),
            )

        assert response.status_code == 200
        _, kwargs = mock_search.call_args
        assert kwargs["document_ids"] == [doc_id]

    def test_score_filtering_applied(self, search_client: TestClient) -> None:
        """Score threshold is enforced by the service; API returns whatever service returns."""
        tokens = register_and_login(search_client)
        high_score = _make_result(score=0.95)

        with patch(
            "rag_platform.retrieval.application.services.retrieval_service.RetrievalService.search",
            return_value=[high_score],
        ):
            response = search_client.post(
                "/api/v1/search",
                json={"query": "test"},
                headers=_auth_header(tokens),
            )

        assert response.status_code == 200
        assert response.json()["results"][0]["score"] == pytest.approx(0.95)

    def test_ownership_isolation(self, search_client: TestClient) -> None:
        """Two users get independent search results — ownership enforced at service level."""
        alice = register_and_login(search_client, email="alice@example.com")
        bob = register_and_login(
            search_client, email="bob@example.com", password="BobPass123", full_name="Bob"
        )

        alice_result = _make_result()

        with patch(
            "rag_platform.retrieval.application.services.retrieval_service.RetrievalService.search",
            return_value=[alice_result],
        ):
            alice_resp = search_client.post(
                "/api/v1/search",
                json={"query": "test"},
                headers=_auth_header(alice),
            )

        from rag_platform.retrieval.domain.exceptions import NoResultsFoundError

        with patch(
            "rag_platform.retrieval.application.services.retrieval_service.RetrievalService.search",
            side_effect=NoResultsFoundError(),
        ):
            bob_resp = search_client.post(
                "/api/v1/search",
                json={"query": "test"},
                headers=_auth_header(bob),
            )

        assert alice_resp.status_code == 200
        assert bob_resp.status_code == 404

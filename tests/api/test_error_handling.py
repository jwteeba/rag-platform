"""API-level tests proving the error-handling middleware normalizes errors.

A throwaway route is mounted onto a fresh app instance for this test module
only, so we can assert on the RFC 7807 response shape without needing a real
domain endpoint that raises errors (none exist yet in Phase 1).
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.core.exceptions import NotFoundError
from rag_platform.main import create_app
from tests.conftest import TEST_DATABASE_URL, TEST_MINIO_BUCKET, TEST_MINIO_ENDPOINT, TEST_REDIS_URL


@pytest.fixture
def mock_minio() -> Iterator[MagicMock]:
    mock = MagicMock()
    mock.bucket_exists.return_value = True
    with patch("rag_platform.core.storage.build_minio_client", return_value=mock):
        yield mock


@pytest.fixture
def client_with_error_route(
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
    )
    app = create_app(settings=settings)

    @app.get("/__test-not-found__")
    async def raise_not_found() -> None:
        raise NotFoundError("Widget not found.")

    @app.get("/__test-unhandled__")
    async def raise_unhandled() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


class TestErrorHandlingMiddleware:
    def test_application_error_returns_rfc7807_shape(
        self, client_with_error_route: TestClient
    ) -> None:
        response = client_with_error_route.get("/__test-not-found__")

        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"

        body = response.json()
        assert body["type"] == "https://errors.rag-platform.dev/not-found"
        assert body["title"] == "Not Found"
        assert body["status"] == 404
        assert body["detail"] == "Widget not found."
        assert body["instance"] == "/__test-not-found__"
        assert "request_id" in body

    def test_unhandled_exception_returns_500_problem_json(
        self, client_with_error_route: TestClient
    ) -> None:
        response = client_with_error_route.get("/__test-unhandled__")

        assert response.status_code == 500
        body = response.json()
        assert body["type"] == "https://errors.rag-platform.dev/internal-server-error"
        assert body["status"] == 500
        assert "unexpected error" in body["detail"].lower()

"""API tests for `/documents/*` endpoints."""

from __future__ import annotations

import io
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.main import create_app
from tests.api.identity_access.conftest import register_and_login
from tests.conftest import TEST_DATABASE_URL, TEST_MINIO_BUCKET, TEST_MINIO_ENDPOINT, TEST_REDIS_URL

PDF_BYTES = b"%PDF-1.4 fake pdf content"
PDF_CONTENT_TYPE = "application/pdf"


def _auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def mock_minio_client() -> Iterator[MagicMock]:
    """Replace the MinIO client with a mock for all API tests.

    The mock makes `bucket_exists` return True (so the startup hook and
    health check pass) and stubs out put_object / remove_object /
    presigned_get_object so no real S3 calls are made.
    """
    mock = MagicMock()
    mock.bucket_exists.return_value = True
    mock.put_object.return_value = None
    mock.remove_object.return_value = None
    mock.presigned_get_object.return_value = "https://minio.example.com/presigned"
    with patch("rag_platform.core.storage.build_minio_client", return_value=mock):
        yield mock


@pytest.fixture
def doc_client(
    clean_database: None,
    clean_cache: None,
    mock_minio_client: MagicMock,
) -> Iterator[TestClient]:
    """TestClient with a mocked MinIO client."""
    settings = Settings(
        environment=Environment.TESTING,
        log_format=LogFormat.JSON,
        cors_allowed_origins=["http://testserver"],
        allowed_hosts=["*"],
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
        minio_endpoint=TEST_MINIO_ENDPOINT,
        minio_bucket=TEST_MINIO_BUCKET,
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
        minio_secure=False,
    )
    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c


def _upload(client: TestClient, tokens: dict[str, str], *, content: bytes = PDF_BYTES) -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/api/v1/documents",
        files={"file": ("test.pdf", io.BytesIO(content), PDF_CONTENT_TYPE)},
        headers=_auth_header(tokens),
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestUpload:
    def test_upload_returns_201_with_document_shape(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)

        response = doc_client.post(
            "/api/v1/documents",
            files={"file": ("report.pdf", io.BytesIO(PDF_BYTES), PDF_CONTENT_TYPE)},
            headers=_auth_header(tokens),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "report.pdf"
        assert body["content_type"] == PDF_CONTENT_TYPE
        assert body["size_bytes"] == len(PDF_BYTES)
        assert "id" in body
        assert "storage_key" in body

    def test_upload_requires_auth(self, doc_client: TestClient) -> None:
        response = doc_client.post(
            "/api/v1/documents",
            files={"file": ("f.pdf", io.BytesIO(PDF_BYTES), PDF_CONTENT_TYPE)},
        )
        assert response.status_code == 401

    def test_upload_empty_file_returns_422(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)

        response = doc_client.post(
            "/api/v1/documents",
            files={"file": ("empty.pdf", io.BytesIO(b""), PDF_CONTENT_TYPE)},
            headers=_auth_header(tokens),
        )

        assert response.status_code == 422

    def test_upload_unsupported_type_returns_422(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)

        response = doc_client.post(
            "/api/v1/documents",
            files={"file": ("img.png", io.BytesIO(b"PNG"), "image/png")},
            headers=_auth_header(tokens),
        )

        assert response.status_code == 422


class TestList:
    def test_list_returns_own_documents(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        _upload(doc_client, tokens)

        response = doc_client.get("/api/v1/documents", headers=_auth_header(tokens))

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1

    def test_list_does_not_return_other_users_documents(self, doc_client: TestClient) -> None:
        alice = register_and_login(doc_client, email="alice@example.com")
        bob = register_and_login(
            doc_client, email="bob@example.com", password="BobPass123", full_name="Bob"
        )
        _upload(doc_client, alice)

        response = doc_client.get("/api/v1/documents", headers=_auth_header(bob))

        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_list_requires_auth(self, doc_client: TestClient) -> None:
        assert doc_client.get("/api/v1/documents").status_code == 401


class TestGet:
    def test_get_returns_document(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        doc = _upload(doc_client, tokens)

        response = doc_client.get(f"/api/v1/documents/{doc['id']}", headers=_auth_header(tokens))

        assert response.status_code == 200
        assert response.json()["id"] == doc["id"]

    def test_get_unknown_returns_404(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        import uuid

        response = doc_client.get(f"/api/v1/documents/{uuid.uuid4()}", headers=_auth_header(tokens))

        assert response.status_code == 404

    def test_get_other_users_document_returns_404(self, doc_client: TestClient) -> None:
        alice = register_and_login(doc_client, email="alice@example.com")
        bob = register_and_login(
            doc_client, email="bob@example.com", password="BobPass123", full_name="Bob"
        )
        doc = _upload(doc_client, alice)

        response = doc_client.get(f"/api/v1/documents/{doc['id']}", headers=_auth_header(bob))

        assert response.status_code == 404


class TestDownloadUrl:
    def test_download_url_returns_url(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        doc = _upload(doc_client, tokens)

        response = doc_client.get(
            f"/api/v1/documents/{doc['id']}/download-url",
            headers=_auth_header(tokens),
        )

        assert response.status_code == 200
        assert "url" in response.json()

    def test_download_redirects(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        doc = _upload(doc_client, tokens)

        response = doc_client.get(
            f"/api/v1/documents/{doc['id']}/download",
            headers=_auth_header(tokens),
            follow_redirects=False,
        )

        assert response.status_code == 307
        assert response.headers["location"]


class TestDelete:
    def test_delete_returns_204(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        doc = _upload(doc_client, tokens)

        response = doc_client.delete(f"/api/v1/documents/{doc['id']}", headers=_auth_header(tokens))

        assert response.status_code == 204

    def test_deleted_document_no_longer_accessible(self, doc_client: TestClient) -> None:
        tokens = register_and_login(doc_client)
        doc = _upload(doc_client, tokens)
        doc_client.delete(f"/api/v1/documents/{doc['id']}", headers=_auth_header(tokens))

        response = doc_client.get(f"/api/v1/documents/{doc['id']}", headers=_auth_header(tokens))

        assert response.status_code == 404

    def test_delete_other_users_document_returns_404(self, doc_client: TestClient) -> None:
        alice = register_and_login(doc_client, email="alice@example.com")
        bob = register_and_login(
            doc_client, email="bob@example.com", password="BobPass123", full_name="Bob"
        )
        doc = _upload(doc_client, alice)

        response = doc_client.delete(f"/api/v1/documents/{doc['id']}", headers=_auth_header(bob))

        assert response.status_code == 404

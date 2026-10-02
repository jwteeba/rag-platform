"""API tests for prompt template CRUD and context assembly endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.main import create_app
from tests.api.identity_access.conftest import admin_tokens, register_and_login
from tests.conftest import TEST_DATABASE_URL, TEST_MINIO_BUCKET, TEST_MINIO_ENDPOINT, TEST_REDIS_URL

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "AdminPass123"


def _auth(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def mock_minio() -> Iterator[MagicMock]:
    mock = MagicMock()
    mock.bucket_exists.return_value = True
    with patch("rag_platform.core.storage.build_minio_client", return_value=mock):
        yield mock


@pytest.fixture
def gen_client(
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
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=ADMIN_PASSWORD,
    )
    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c


def _admin_tokens(client: TestClient) -> dict[str, str]:
    return admin_tokens(client)


VALID_TEMPLATE = {
    "name": "test-template",
    "system_prompt": "You are helpful.",
    "user_template": "Context:\n{context}\n\nQuestion: {query}\n\nAnswer:",
    "model_target": "gpt-4o",
}


class TestPromptTemplateCRUD:
    def test_create_requires_admin(self, gen_client: TestClient) -> None:
        member = register_and_login(gen_client)
        response = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(member)
        )
        assert response.status_code == 403

    def test_create_returns_201(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        response = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens)
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "test-template"
        assert "id" in body

    def test_create_duplicate_name_returns_409(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        gen_client.post("/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens))
        response = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens)
        )
        assert response.status_code == 409

    def test_list_returns_seeded_defaults(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        response = gen_client.get("/api/v1/prompt-templates", headers=_auth(tokens))
        assert response.status_code == 200
        names = [t["name"] for t in response.json()["items"]]
        assert "general-qa" in names
        assert "summarization" in names

    def test_get_returns_template(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        created = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens)
        ).json()
        response = gen_client.get(
            f"/api/v1/prompt-templates/{created['id']}", headers=_auth(tokens)
        )
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_unknown_returns_404(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        response = gen_client.get(f"/api/v1/prompt-templates/{uuid.uuid4()}", headers=_auth(tokens))
        assert response.status_code == 404

    def test_patch_updates_field(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        created = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens)
        ).json()
        response = gen_client.patch(
            f"/api/v1/prompt-templates/{created['id']}",
            json={"system_prompt": "Updated."},
            headers=_auth(tokens),
        )
        assert response.status_code == 200
        assert response.json()["system_prompt"] == "Updated."

    def test_patch_empty_body_returns_422(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        created = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens)
        ).json()
        response = gen_client.patch(
            f"/api/v1/prompt-templates/{created['id']}", json={}, headers=_auth(tokens)
        )
        assert response.status_code == 422

    def test_delete_returns_204(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        created = gen_client.post(
            "/api/v1/prompt-templates", json=VALID_TEMPLATE, headers=_auth(tokens)
        ).json()
        response = gen_client.delete(
            f"/api/v1/prompt-templates/{created['id']}", headers=_auth(tokens)
        )
        assert response.status_code == 204

    def test_delete_unknown_returns_404(self, gen_client: TestClient) -> None:
        tokens = _admin_tokens(gen_client)
        response = gen_client.delete(
            f"/api/v1/prompt-templates/{uuid.uuid4()}", headers=_auth(tokens)
        )
        assert response.status_code == 404


class TestAssembleEndpoint:
    def test_assemble_requires_auth(self, gen_client: TestClient) -> None:
        response = gen_client.post(
            "/api/v1/prompt-templates/assemble",
            json={"query": "What is Python?", "chunks": []},
        )
        assert response.status_code == 401

    def test_assemble_returns_assembled_prompt(self, gen_client: TestClient) -> None:
        member = register_and_login(gen_client)
        chunk = {
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "filename": "guide.pdf",
            "content": "Python is a high-level programming language.",
            "score": 0.9,
            "chunk_index": 0,
        }
        response = gen_client.post(
            "/api/v1/prompt-templates/assemble",
            json={"query": "What is Python?", "chunks": [chunk]},
            headers=_auth(member),
        )
        assert response.status_code == 200
        body = response.json()
        assert "system_prompt" in body
        assert "rendered_context" in body
        assert "guide.pdf" in body["rendered_context"]
        assert body["token_count"] > 0
        assert len(body["source_chunks"]) == 1
        assert body["source_chunks"][0]["filename"] == "guide.pdf"

    def test_assemble_with_unknown_template_id_returns_404(self, gen_client: TestClient) -> None:
        member = register_and_login(gen_client)
        response = gen_client.post(
            "/api/v1/prompt-templates/assemble",
            json={
                "query": "test",
                "chunks": [],
                "template_id": str(uuid.uuid4()),
            },
            headers=_auth(member),
        )
        assert response.status_code == 404

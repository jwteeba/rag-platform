"""Shared fixtures and helpers for identity_access API tests."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.main import create_app
from tests.conftest import TEST_DATABASE_URL

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "AdminPass123"


@pytest.fixture
def admin_settings(clean_database: None) -> Settings:
    """Settings with a bootstrap admin configured, for RBAC-admin test cases."""
    return Settings(
        environment=Environment.TESTING,
        log_format=LogFormat.JSON,
        allowed_hosts=["*"],
        database_url=TEST_DATABASE_URL,
        bootstrap_admin_email=ADMIN_EMAIL,
        bootstrap_admin_password=ADMIN_PASSWORD,
    )


@pytest.fixture
def admin_client(admin_settings: Settings) -> Iterator[TestClient]:
    """A `TestClient` whose app has a bootstrap ADMIN-role user pre-created."""
    app = create_app(settings=admin_settings)
    with TestClient(app) as test_client:
        yield test_client


def register(
    client: TestClient,
    *,
    email: str = "alice@example.com",
    password: str = "AlicePass123",
    full_name: str = "Alice Example",
) -> httpx.Response:
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )


def login(client: TestClient, *, email: str, password: str) -> httpx.Response:
    return client.post("/api/v1/auth/login", data={"username": email, "password": password})


def register_and_login(
    client: TestClient,
    *,
    email: str = "alice@example.com",
    password: str = "AlicePass123",
    full_name: str = "Alice Example",
) -> dict[str, str]:
    """Register a new MEMBER user and return their token pair as a dict."""
    register(client, email=email, password=password, full_name=full_name)
    response = login(client, email=email, password=password)
    assert response.status_code == 200, response.text
    return response.json()


def admin_tokens(admin_client: TestClient) -> dict[str, str]:
    """Log in as the pre-seeded bootstrap admin and return the token pair."""
    response = login(admin_client, email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
    assert response.status_code == 200, response.text
    return response.json()


def auth_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}

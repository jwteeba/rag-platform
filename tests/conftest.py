"""Shared pytest fixtures.

Kept intentionally minimal in Phase 1 — no database, cache, or external
service fixtures exist yet because nothing in the codebase uses them yet.
Those are added in the phases that introduce the corresponding
infrastructure (Phase 3 for DB fixtures, Phase 4 for Redis, etc.).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Settings tuned for the test environment.

    Uses JSON log format to exercise that code path in CI (console rendering
    is covered implicitly by local `make dev` runs) and marks the
    environment as TESTING so `settings.is_testing` behaves correctly for
    any test that depends on it.
    """
    return Settings(
        environment=Environment.TESTING,
        log_format=LogFormat.JSON,
        cors_allowed_origins=["http://testserver"],
        allowed_hosts=["*"],
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    """A `TestClient` bound to an app instance built from `test_settings`."""
    app = create_app(settings=test_settings)
    with TestClient(app) as test_client:
        yield test_client

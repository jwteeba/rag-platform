"""Shared pytest fixtures.

As of Phase 3, `client`/`admin_client`-based API tests run against a real
Postgres database (see `TEST_DATABASE_URL` below) rather than the Phase 1-2
in-memory stores — `clean_database` creates the schema (idempotent) and
truncates every table before each test that needs it, giving each test a
known-empty starting state despite Postgres persisting across tests, unlike
the in-memory adapters that reset automatically with every new app instance.

Pure `tests/unit/*` tests that exercise ports/services directly with
in-memory adapters do NOT depend on `clean_database` and have no Postgres
dependency at all — only fixtures that build a full app (`client`,
`admin_client`) pull it in, since only those touch the DI container's real
engine.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.core.db import Base
from rag_platform.main import create_app

# `Settings` (used by the running app) loads `.env` itself via
# pydantic-settings, but that parsing is internal to `Settings` and does
# NOT populate the real process environment — so `os.getenv` below would
# never see an `APP_TEST_DATABASE_URL` set only in `.env`, without this
# explicit load. `override=False` so a real shell-exported value (e.g. in
# CI) always wins over whatever's in `.env`.
load_dotenv(override=False)

# A dedicated test database — never the same one `make dev` points at, so
# running the suite can never truncate development data. See
# `docs/architecture.md` / README for how to create it locally.
#
# Overridable via `APP_TEST_DATABASE_URL` for machines where the default
# (`localhost:5432`) collides with something else — a locally-installed
# Postgres, a remapped Docker port, etc. Deliberately a *separate* env var
# from `APP_DATABASE_URL` (which `Settings`/the running app reads) rather
# than falling back to it: the test suite must never silently inherit
# whatever database the app happens to be pointed at, since a stray real
# database there would get truncated by `clean_database` below.
TEST_DATABASE_URL = os.getenv(
    "APP_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_platform_test",
)


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    """Ensure the schema exists and every table is empty before a test runs.

    `create_all` is idempotent (checks for each table's existence first),
    so this is safe to run before every test rather than only once per
    session — simpler than coordinating a session-scoped async fixture with
    pytest-asyncio's per-test event loop, at a small, acceptable per-test
    cost.
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text("TRUNCATE TABLE refresh_tokens, users RESTART IDENTITY CASCADE")
        )
    await engine.dispose()
    yield


@pytest.fixture
def test_settings(clean_database: None) -> Settings:
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
        database_url=TEST_DATABASE_URL,
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    """A `TestClient` bound to an app instance built from `test_settings`."""
    app = create_app(settings=test_settings)
    with TestClient(app) as test_client:
        yield test_client

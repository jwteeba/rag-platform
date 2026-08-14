"""Shared pytest fixtures.

As of Phase 3, `client`/`admin_client`-based API tests run against a real
Postgres database (see `TEST_DATABASE_URL` below) rather than the Phase 1-2
in-memory stores — `clean_database` creates the schema (idempotent) and
truncates every table before each test that needs it, giving each test a
known-empty starting state despite Postgres persisting across tests, unlike
the in-memory adapters that reset automatically with every new app instance.

As of Phase 4, the same applies to Redis (`TEST_REDIS_URL`,
`clean_cache`) — every key under the test run's logical DB is flushed
before each test that needs it, for the same reason.

Pure `tests/unit/*` tests that exercise ports/services directly with
in-memory adapters do NOT depend on `clean_database`/`clean_cache` and have
no Postgres/Redis dependency at all — only fixtures that build a full app
(`client`, `admin_client`) pull them in, since only those touch the DI
container's real engine/Redis client.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.core.db import Base

# `Base.metadata` only knows about a table once its model class has been
# imported somewhere in this process — table registration is a side effect
# of the class body executing, not automatic. `clean_database` below calls
# `Base.metadata.create_all()`, which needs every bounded context's models
# already registered to resolve cross-table foreign keys (e.g.
# `refresh_tokens.user_id` → `users.id`).
#
# Without this explicit import, registration depended on whatever test
# files pytest happened to have already collected importing these models
# transitively (e.g. via `PostgresUserRepository`) — usually true for the
# full suite, but NOT guaranteed for a narrower run (a single test file, a
# `-k` selection, a new test that doesn't touch these repositories), which
# surfaces as `NoReferencedTableError: ... could not find table 'users'`.
# Importing every context's models explicitly here, mirroring what
# `alembic/env.py` already has to do for the same reason, removes that
# fragility rather than depending on incidental import order.
from rag_platform.identity_access.infrastructure import (
    models as _identity_access_models,  # noqa: F401
)
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

# Same rationale as TEST_DATABASE_URL above, for Redis. Logical DB index 1
# (`/1`), not 0 — so even someone pointing this at a real, shared Redis
# instance's default DB doesn't collide with `make dev`'s keyspace.
# Overridable via APP_TEST_REDIS_URL for the same reasons as above (Docker
# port remaps, local install collisions).
TEST_REDIS_URL = os.getenv("APP_TEST_REDIS_URL", "redis://localhost:6379/1")


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
async def clean_cache() -> AsyncIterator[None]:
    """Flush the test run's logical Redis DB before a test runs.

    `FLUSHDB` (not `FLUSHALL`) — only clears the logical DB this test suite
    uses (index 1), never any other DB a shared Redis instance might hold.
    """
    client: Redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    await client.aclose()
    yield


@pytest.fixture
def test_settings(clean_database: None, clean_cache: None) -> Settings:
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
        redis_url=TEST_REDIS_URL,
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    """A `TestClient` bound to an app instance built from `test_settings`."""
    app = create_app(settings=test_settings)
    with TestClient(app) as test_client:
        yield test_client

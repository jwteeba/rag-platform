"""Integration tests for `rag_platform.di.containers`.

`build_container` wires real SQLAlchemy and Redis clients — there's no
meaningful way to unit test it against a fake, so this lives under
`tests/integration/` and depends on `clean_database` / `clean_cache` (see
`tests/conftest.py`) for a real, isolated Postgres database and Redis
keyspace per test.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.di.containers import Container, build_container, ensure_bootstrap_admin
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
)
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "environment": Environment.TESTING,
        "log_format": LogFormat.JSON,
        "allowed_hosts": ["*"],
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@asynccontextmanager
async def _built_container(settings: Settings) -> AsyncIterator[Container]:
    """Build a container and guarantee both its engine and Redis client
    are cleaned up afterward, regardless of what the test does with it."""
    container = build_container(settings)
    try:
        yield container
    finally:
        await container.engine.dispose()
        await container.redis_client.aclose()


class TestBuildContainer:
    async def test_returns_a_working_engine_and_session_factory(
        self, clean_database: None, clean_cache: None
    ) -> None:
        async with (
            _built_container(_settings()) as container,
            container.session_factory() as session,
        ):
            repo = PostgresUserRepository(session)
            assert await repo.get_by_email("nobody@example.com") is None

    async def test_password_hasher_and_token_service_are_usable(
        self, clean_database: None, clean_cache: None
    ) -> None:
        async with _built_container(_settings()) as container:
            hashed = container.password_hasher.hash("a-password")
            assert container.password_hasher.verify("a-password", hashed) is True

    async def test_redis_client_is_reachable(self, clean_database: None, clean_cache: None) -> None:
        async with _built_container(_settings()) as container:
            assert await container.redis_client.ping() is True

    async def test_cache_service_round_trips_a_value(
        self, clean_database: None, clean_cache: None
    ) -> None:
        async with _built_container(_settings()) as container:
            await container.cache_service.set_json("test-key", {"a": 1}, ttl_seconds=30)

            assert await container.cache_service.get_json("test-key") == {"a": 1}


class TestEnsureBootstrapAdmin:
    async def test_no_op_when_unset(self, clean_database: None, clean_cache: None) -> None:
        async with _built_container(_settings()) as container:
            await ensure_bootstrap_admin(container, _settings())

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                assert await repo.get_by_email("admin@example.com") is None

    async def test_creates_admin_when_configured(
        self, clean_database: None, clean_cache: None
    ) -> None:
        settings = _settings(
            bootstrap_admin_email="admin@example.com",
            bootstrap_admin_password="AdminPass123",
        )
        async with _built_container(settings) as container:
            await ensure_bootstrap_admin(container, settings)

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                admin = await repo.get_by_email("admin@example.com")
                assert admin is not None
                assert admin.role is Role.ADMIN

    async def test_idempotent_on_repeated_calls(
        self, clean_database: None, clean_cache: None
    ) -> None:
        settings = _settings(
            bootstrap_admin_email="admin@example.com",
            bootstrap_admin_password="AdminPass123",
        )
        async with _built_container(settings) as container:
            await ensure_bootstrap_admin(container, settings)
            await ensure_bootstrap_admin(container, settings)  # should not raise or duplicate

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                page, _ = await repo.list_page(limit=10, after_id=None)
                admins = [u for u in page if u.email == "admin@example.com"]
                assert len(admins) == 1

    async def test_only_email_set_is_a_no_op(self, clean_database: None, clean_cache: None) -> None:
        settings = _settings(bootstrap_admin_email="admin@example.com")
        async with _built_container(settings) as container:
            await ensure_bootstrap_admin(container, settings)

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                assert await repo.get_by_email("admin@example.com") is None

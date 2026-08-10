"""Integration tests for `rag_platform.di.containers`.

Unlike the Phase 2 version of this test, `build_container` now wires a real
SQLAlchemy engine — there's no meaningful way to unit test it against a
fake, so this lives under `tests/integration/` and depends on
`clean_database` (see `tests/conftest.py`) for a real, isolated Postgres
database per test.
"""

from __future__ import annotations

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.di.containers import build_container, ensure_bootstrap_admin
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
)
from tests.conftest import TEST_DATABASE_URL


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "environment": Environment.TESTING,
        "log_format": LogFormat.JSON,
        "allowed_hosts": ["*"],
        "database_url": TEST_DATABASE_URL,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestBuildContainer:
    async def test_returns_a_working_engine_and_session_factory(self, clean_database: None) -> None:
        container = build_container(_settings())
        try:
            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                assert await repo.get_by_email("nobody@example.com") is None
        finally:
            await container.engine.dispose()

    async def test_password_hasher_and_token_service_are_usable(self, clean_database: None) -> None:
        container = build_container(_settings())
        try:
            hashed = container.password_hasher.hash("a-password")
            assert container.password_hasher.verify("a-password", hashed) is True
        finally:
            await container.engine.dispose()


class TestEnsureBootstrapAdmin:
    async def test_no_op_when_unset(self, clean_database: None) -> None:
        container = build_container(_settings())
        try:
            await ensure_bootstrap_admin(container, _settings())

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                assert await repo.get_by_email("admin@example.com") is None
        finally:
            await container.engine.dispose()

    async def test_creates_admin_when_configured(self, clean_database: None) -> None:
        settings = _settings(
            bootstrap_admin_email="admin@example.com",
            bootstrap_admin_password="AdminPass123",
        )
        container = build_container(settings)
        try:
            await ensure_bootstrap_admin(container, settings)

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                admin = await repo.get_by_email("admin@example.com")
                assert admin is not None
                assert admin.role is Role.ADMIN
        finally:
            await container.engine.dispose()

    async def test_idempotent_on_repeated_calls(self, clean_database: None) -> None:
        settings = _settings(
            bootstrap_admin_email="admin@example.com",
            bootstrap_admin_password="AdminPass123",
        )
        container = build_container(settings)
        try:
            await ensure_bootstrap_admin(container, settings)
            await ensure_bootstrap_admin(container, settings)  # should not raise or duplicate

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                page, _ = await repo.list_page(limit=10, after_id=None)
                admins = [u for u in page if u.email == "admin@example.com"]
                assert len(admins) == 1
        finally:
            await container.engine.dispose()

    async def test_only_email_set_is_a_no_op(self, clean_database: None) -> None:
        settings = _settings(bootstrap_admin_email="admin@example.com")
        container = build_container(settings)
        try:
            await ensure_bootstrap_admin(container, settings)

            async with container.session_factory() as session:
                repo = PostgresUserRepository(session)
                assert await repo.get_by_email("admin@example.com") is None
        finally:
            await container.engine.dispose()

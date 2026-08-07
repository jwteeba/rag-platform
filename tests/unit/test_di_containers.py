"""Unit tests for `rag_platform.di.containers`."""

from __future__ import annotations

from rag_platform.core.config import Environment, LogFormat, Settings
from rag_platform.di.containers import build_container, ensure_bootstrap_admin
from rag_platform.identity_access.domain.roles import Role


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "environment": Environment.TESTING,
        "log_format": LogFormat.JSON,
        "allowed_hosts": ["*"],
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestBuildContainer:
    def test_returns_wired_services(self) -> None:
        container = build_container(_settings())

        assert container.auth_service is not None
        assert container.user_service is not None

    def test_auth_service_and_user_service_share_the_same_user_repository(self) -> None:
        """A user registered via auth_service must be visible via user_service."""
        container = build_container(_settings())

        assert container.user_service._users is container.user_repository


class TestEnsureBootstrapAdmin:
    async def test_no_op_when_unset(self) -> None:
        container = build_container(_settings())

        await ensure_bootstrap_admin(container, _settings())

        assert await container.user_repository.get_by_email("admin@example.com") is None

    async def test_creates_admin_when_configured(self) -> None:
        settings = _settings(
            bootstrap_admin_email="admin@example.com",
            bootstrap_admin_password="AdminPass123",
        )
        container = build_container(settings)

        await ensure_bootstrap_admin(container, settings)

        admin = await container.user_repository.get_by_email("admin@example.com")
        assert admin is not None
        assert admin.role is Role.ADMIN

    async def test_idempotent_on_repeated_calls(self) -> None:
        settings = _settings(
            bootstrap_admin_email="admin@example.com",
            bootstrap_admin_password="AdminPass123",
        )
        container = build_container(settings)

        await ensure_bootstrap_admin(container, settings)
        await ensure_bootstrap_admin(container, settings)  # should not raise or duplicate

        page = await container.user_repository.list_page(limit=10, after_id=None)
        admins = [u for u in page[0] if u.email == "admin@example.com"]
        assert len(admins) == 1

    async def test_only_email_set_is_a_no_op(self) -> None:
        settings = _settings(bootstrap_admin_email="admin@example.com")
        container = build_container(settings)

        await ensure_bootstrap_admin(container, settings)

        assert await container.user_repository.get_by_email("admin@example.com") is None

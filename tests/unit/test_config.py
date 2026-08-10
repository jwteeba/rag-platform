"""Unit tests for `rag_platform.core.config`."""

from __future__ import annotations

import pytest

from rag_platform.core.config import Environment, LogLevel, Settings, get_settings


class TestSettingsDefaults:
    def test_default_environment_is_development(self) -> None:
        settings = Settings(_env_file=None)

        assert settings.environment is Environment.DEVELOPMENT
        assert settings.is_development is True
        assert settings.is_production is False
        assert settings.is_testing is False

    def test_default_log_level_is_info(self) -> None:
        settings = Settings(_env_file=None)

        assert settings.log_level is LogLevel.INFO

    def test_default_port_is_8000(self) -> None:
        settings = Settings(_env_file=None)

        assert settings.port == 8000


class TestSettingsEnvParsing:
    def test_reads_environment_variable_with_app_prefix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        # A real secret is required in production (see
        # TestProductionSafety below) — set one so this test stays focused
        # on env-var parsing rather than that separate validation rule.
        monkeypatch.setenv("APP_JWT_SECRET_KEY", "a-real-production-secret")

        settings = Settings(_env_file=None)

        assert settings.environment is Environment.PRODUCTION
        assert settings.is_production is True

    def test_comma_separated_cors_origins_are_split(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "APP_CORS_ALLOWED_ORIGINS", "https://a.example.com, https://b.example.com"
        )

        settings = Settings(_env_file=None)

        assert settings.cors_allowed_origins == ["https://a.example.com", "https://b.example.com"]

    def test_empty_cors_origins_defaults_to_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APP_CORS_ALLOWED_ORIGINS", raising=False)

        settings = Settings(_env_file=None)

        assert settings.cors_allowed_origins == []

    def test_invalid_port_raises_validation_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_PORT", "70000")

        with pytest.raises(ValueError, match="less than or equal to 65535"):
            Settings(_env_file=None)


class TestProductionSafety:
    def test_rejects_default_jwt_secret_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "production")

        with pytest.raises(ValueError, match="APP_JWT_SECRET_KEY must be set"):
            Settings(_env_file=None)

    def test_accepts_a_real_secret_in_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENVIRONMENT", "production")
        monkeypatch.setenv("APP_JWT_SECRET_KEY", "a-real-production-secret")

        settings = Settings(_env_file=None)

        assert settings.jwt_secret_key == "a-real-production-secret"

    def test_default_secret_is_fine_outside_production(self) -> None:
        # Development is the default environment; should not raise.
        settings = Settings(_env_file=None)

        assert settings.jwt_secret_key == "insecure-development-secret-for-testing"


class TestGetSettings:
    def test_returns_cached_instance(self) -> None:
        get_settings.cache_clear()

        first = get_settings()
        second = get_settings()

        assert first is second

        get_settings.cache_clear()

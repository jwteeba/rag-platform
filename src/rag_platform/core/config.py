"""Application configuration.

All runtime configuration is loaded from environment variables (optionally via
a local `.env` file in development) through `pydantic-settings`. No module in
this codebase other than this one may read from `os.environ` directly — every
other layer receives configuration through the `Settings` object below, wired
via dependency injection.

Future phases will add sibling settings groups (e.g. `DatabaseSettings`,
`RedisSettings`, `LLMSettings`) and compose them into `Settings` the same way
`log_level` and friends are composed here. Nothing is stubbed out ahead of
the phase that needs it.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment the application is running in."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Supported structured-logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(StrEnum):
    """Log rendering style.

    CONSOLE is human-readable and colorized, intended for local development.
    JSON is machine-parseable, intended for production log aggregation.
    """

    CONSOLE = "console"
    JSON = "json"


class Settings(BaseSettings):
    """Root application settings.

    Values are read from environment variables prefixed with `APP_`, with an
    optional `.env` file as a fallback in local development. Environment
    variables always take precedence over `.env` file values.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    name: str = "rag-platform"
    version: str = "0.1.0"

    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.CONSOLE

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    api_v1_prefix: str = "/api/v1"

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    @field_validator("cors_allowed_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """Allow comma-separated env values to populate list fields.

        These fields are marked `NoDecode` so pydantic-settings hands us the
        raw string from the environment instead of attempting to JSON-decode
        it (which would fail for the common ops-friendly comma-separated
        format used in `.env` files). We do the splitting ourselves here.
        """
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.environment is Environment.TESTING

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide `Settings` instance.

    Cached with `lru_cache` so the environment is only parsed once per
    process. Tests that need a different configuration should override the
    `get_settings` FastAPI dependency rather than mutating this cache.
    """
    return Settings()

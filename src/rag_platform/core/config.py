"""Application configuration.

All runtime configuration is loaded from environment variables (optionally via
a local `.env` file in development) through `pydantic-settings`. No module in
this codebase other than this one may read from `os.environ` directly — every
other layer receives configuration through the `Settings` object below, wired
via dependency injection.

Settings groups are added flat (prefixed, e.g. `jwt_*`, `database_*`) rather
than as nested sub-settings objects — simpler env-var mapping with
`pydantic-settings`, and consistent with how `log_level` and friends already
work. Nothing is stubbed out ahead of the phase that needs it.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
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

    # -- Authentication (Phase 2) -----------------------------------------
    # HMAC secret used to sign/verify JWTs. The default is safe only for
    # local development because `is_production` is checked at startup (see
    # `main.py`) and refuses to boot with the default in production.
    jwt_secret_key: str = "insecure-development-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)

    # Optional convenience for local/dev environments: if both are set, the
    # application ensures a single ADMIN-role user exists with these
    # credentials on startup. Unset (the default) in any environment where
    # this isn't wanted, including production unless deliberately supplied
    # through a real secret store.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # -- Database (Phase 3) ------------------------------------------------
    # `+asyncpg` because every DB call in this codebase is async (repository
    # ports are `async def` throughout); a sync driver would silently block
    # the event loop.
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_platform"
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    # Logs every SQL statement — verbose, dev/debugging only.
    database_echo: bool = False

    # -- Cache / Redis (Phase 4) --------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = Field(default=20, ge=1)
    # Default TTL for cached refresh-token revocation lookups (see
    # `identity_access/infrastructure/repositories/cached_refresh_token_store.py`).
    # Deliberately short — a stale "not revoked" cache entry is a genuine
    # (if small) security exposure window: a token revoked via logout could
    # still read as valid from cache for up to this long. Individual cache
    # entries also get evicted early, at the token's own expiry, whichever
    # comes first.
    refresh_token_cache_ttl_seconds: int = Field(default=60, ge=1)

    # -- Background tasks / Celery (Phase 6) -------------------------------
    # Redis is already a required platform dependency.  Keep the broker and
    # result backend on its application URL by default, while allowing ops to
    # point either one at an isolated Redis logical DB/instance when needed.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = True
    celery_task_time_limit_seconds: int = Field(default=300, ge=1)
    celery_task_soft_time_limit_seconds: int = Field(default=270, ge=1)

    # -- Object storage / MinIO (Phase 5) -----------------------------------
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket: str = "rag-platform"
    # Seconds a presigned download URL remains valid.
    minio_presigned_expiry_seconds: int = Field(default=3600, ge=1)

    # -- Upload constraints (Phase 5) ---------------------------------------
    upload_max_size_bytes: int = Field(default=50 * 1024 * 1024, ge=1)  # 50 MB
    upload_allowed_content_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
    )

    # -- Document processing / chunking (Phase 7) --------------------------
    # Token means whitespace-delimited token here; Phase 8 can replace this
    # approximation with the embedding model tokenizer without changing the
    # persistence contract.
    chunk_size_tokens: int = Field(default=500, ge=1)
    chunk_overlap_tokens: int = Field(default=50, ge=0)
    max_chunks_per_document: int = Field(default=1_000, ge=1)

    @model_validator(mode="after")
    def _reject_default_jwt_secret_in_production(self) -> Settings:
        """Fail fast at startup rather than silently signing production JWTs
        with a publicly-known development secret."""
        if self.is_production and self.jwt_secret_key == "insecure-development-secret-change-me":
            raise ValueError(
                "APP_JWT_SECRET_KEY must be set to a real secret when "
                "APP_ENVIRONMENT=production. Refusing to start with the "
                "default development secret."
            )
        return self

    @model_validator(mode="after")
    def _validate_chunk_overlap(self) -> Settings:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
        return self

    @field_validator(
        "cors_allowed_origins", "allowed_hosts", "upload_allowed_content_types", mode="before"
    )
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

    @property
    def resolved_celery_broker_url(self) -> str:
        """Broker URL, defaulting to the existing Redis deployment."""
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        """Result backend URL, defaulting to the existing Redis deployment."""
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide `Settings` instance.

    Cached with `lru_cache` so the environment is only parsed once per
    process. Tests that need a different configuration should override the
    `get_settings` FastAPI dependency rather than mutating this cache.
    """
    return Settings()

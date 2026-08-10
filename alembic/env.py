"""Alembic migration environment.

Two things make this different from Alembic's default template:

1. The database URL comes from `rag_platform.core.config.get_settings()` -
   the same `APP_DATABASE_URL` environment variable the application itself
   reads - rather than a URL hardcoded in `alembic.ini`. One source of
   truth for "which database", whether running the app or running a
   migration.
2. Migrations run over an async engine (`asyncpg`), since the application
   never uses a sync driver. `run_migrations_online` bridges this with
   `AsyncEngine.run_sync`, which is Alembic's documented pattern for async
   dialects - Alembic's own migration execution is inherently synchronous.

Every bounded context's model module must be imported below so its tables
register on `Base.metadata` before `target_metadata` is read - otherwise
`--autogenerate` won't see them.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from rag_platform.core.config import get_settings
from rag_platform.core.db import Base

# Import every bounded context's ORM models so they register on
# `Base.metadata`. Add a line here whenever a new context gains models.
from rag_platform.identity_access.infrastructure import (
    models as identity_access_models,  # noqa: F401
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live DB connection (`alembic upgrade --sql`)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations_sync(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live (async) database connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations_sync)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

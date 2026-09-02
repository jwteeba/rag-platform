"""Shared SQLAlchemy foundation: declarative base, common mixins, and
engine/session factory construction.

Every bounded context's ORM models (e.g.
`identity_access/infrastructure/models.py`) declare against the single
`Base` here, so `Base.metadata` reflects the whole schema in one place —
that's what Alembic's autogenerate compares against (see `alembic/env.py`).

This module is framework-light (SQLAlchemy only, no FastAPI) by design, per
the Shared/Core layering rule — the FastAPI-facing session dependency lives
in `platform/database/dependencies.py` instead.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from rag_platform.core.ids import generate_uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from rag_platform.core.config import Settings


class Base(DeclarativeBase):
    """Declarative base every ORM model in every bounded context inherits from."""


class UUIDPrimaryKeyMixin:
    """A UUIDv7 primary key column, generated application-side.

    Generating the id in Python (rather than via a Postgres `DEFAULT`) keeps
    id generation in one place (`core/ids.py`) shared with anywhere else a
    UUIDv7 is needed, and means a newly-constructed ORM object already has
    its id before the first flush — useful for logging and for building
    related objects in the same unit of work.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=generate_uuid7)


class TimestampMixin:
    """`created_at` / `updated_at` columns, maintained by the database itself.

    Server-side defaults (`server_default=func.now()`, `onupdate=func.now()`)
    rather than application-side `datetime.now()` calls — this way the
    timestamp is correct even for rows inserted or updated by something
    other than this application (a migration backfill, `psql`, etc.), and
    every writer gets a consistent clock instead of each app server's own.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the async SQLAlchemy engine from application settings."""
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=False,
        connect_args={"statement_cache_size": 0},
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory used to open one `AsyncSession` per request."""
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

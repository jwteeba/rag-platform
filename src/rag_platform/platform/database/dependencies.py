"""FastAPI dependency providing a per-request `AsyncSession`.

Pulled from the DI container's session factory (see `di/containers.py`).
One session is opened per request, committed if the request handler
completes without raising, rolled back otherwise, and always closed —
standard unit-of-work-per-request semantics.

Repositories (e.g. `PostgresUserRepository`) receive this session through
their own `Depends()` chain; they never open a session themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session scoped to the current request's lifetime."""
    session_factory = request.app.state.container.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

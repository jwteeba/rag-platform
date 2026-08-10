"""Dependency injection wiring.

This is the *only* place that binds infrastructure implementations to
domain ports. Everywhere else (routes, other services) receives instances
through FastAPI's `Depends()`.

Phase 3 change from Phase 2: `Container` no longer holds pre-built
repositories or application services as process-wide singletons. A
`UserRepositoryPort`/`RefreshTokenStorePort` backed by Postgres needs a
per-request `AsyncSession` — sharing one session across concurrent requests
would let one request's uncommitted writes leak into another's queries and
makes transaction boundaries meaningless. `Container` now holds only the
truly process-wide singletons (the engine, the session factory, the
stateless password hasher and token service); the repositories and
application services built from them are constructed per-request in
`identity_access/api/v1/dependencies.py`, one call each per request thanks
to FastAPI's per-request dependency caching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from rag_platform.core.db import build_engine, build_session_factory
from rag_platform.identity_access.application.dto.auth_dto import RegisterUserInput
from rag_platform.identity_access.application.services.auth_service import AuthenticationService
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.postgres_refresh_token_store import (
    PostgresRefreshTokenStore,
)
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
)
from rag_platform.identity_access.infrastructure.security.jwt_token_service import JWTTokenService
from rag_platform.identity_access.infrastructure.security.password_hasher import (
    BcryptPasswordHasher,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

    from rag_platform.core.config import Settings
    from rag_platform.identity_access.domain.ports import PasswordHasherPort, TokenServicePort


@dataclass(slots=True)
class Container:
    """Process-wide singleton instances, built once at application startup.

    See the module docstring for why repositories and application services
    are *not* held here in Phase 3, unlike Phase 2.
    """

    engine: AsyncEngine
    session_factory: async_sessionmaker[_AsyncSession]
    password_hasher: PasswordHasherPort
    token_service: TokenServicePort


def build_container(settings: Settings) -> Container:
    """Construct the DI container for the given settings.

    `session_factory` opens Postgres-backed
    `PostgresUserRepository` / `PostgresRefreshTokenStore` instances (see ADR-0006).
    """
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    password_hasher = BcryptPasswordHasher()
    token_service = JWTTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        access_token_ttl=timedelta(minutes=settings.access_token_expire_minutes),
        refresh_token_ttl=timedelta(days=settings.refresh_token_expire_days),
    )

    return Container(
        engine=engine,
        session_factory=session_factory,
        password_hasher=password_hasher,
        token_service=token_service,
    )


async def ensure_bootstrap_admin(container: Container, settings: Settings) -> None:
    """Ensure a single ADMIN-role user exists, if configured.

    A dev/local convenience (see `Settings.bootstrap_admin_email`): without
    it, a fresh deployment has no way to reach an admin-only endpoint, since
    self-registration always assigns `Role.MEMBER`. No-op if either setting
    is unset, or if a user with that email already exists (idempotent —
    safe to call on every startup).

    Runs outside the normal per-request dependency chain (there is no
    request during application startup), so it opens and commits its own
    session directly against the container's session factory.
    """
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    async with container.session_factory() as session:
        user_repository = PostgresUserRepository(session)

        existing = await user_repository.get_by_email(settings.bootstrap_admin_email)
        if existing is not None:
            return

        auth_service = AuthenticationService(
            user_repository=user_repository,
            refresh_token_store=PostgresRefreshTokenStore(session),
            password_hasher=container.password_hasher,
            token_service=container.token_service,
        )
        await auth_service.register(
            RegisterUserInput(
                email=settings.bootstrap_admin_email,
                password=settings.bootstrap_admin_password,
                full_name="Bootstrap Admin",
            ),
            role=Role.ADMIN,
        )
        await session.commit()

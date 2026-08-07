"""Dependency injection wiring.

This is the *only* place application services get constructed with concrete
infrastructure implementations bound to their ports. Everywhere else
(routes, other services) receives instances through FastAPI's `Depends()`,
sourced from the container built here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from rag_platform.identity_access.application.dto.auth_dto import RegisterUserInput
from rag_platform.identity_access.application.services.auth_service import AuthenticationService
from rag_platform.identity_access.application.services.user_service import UserService
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.in_memory_refresh_token_store import (
    InMemoryRefreshTokenStore,
)
from rag_platform.identity_access.infrastructure.repositories.in_memory_user_repository import (
    InMemoryUserRepository,
)
from rag_platform.identity_access.infrastructure.security.jwt_token_service import JWTTokenService
from rag_platform.identity_access.infrastructure.security.password_hasher import (
    BcryptPasswordHasher,
)

if TYPE_CHECKING:
    from rag_platform.core.config import Settings
    from rag_platform.identity_access.domain.ports import RefreshTokenStorePort, UserRepositoryPort


@dataclass(slots=True)
class Container:
    """Process-wide singleton instances, built once at application startup."""

    user_repository: UserRepositoryPort
    refresh_token_store: RefreshTokenStorePort
    auth_service: AuthenticationService
    user_service: UserService


def build_container(settings: Settings) -> Container:
    """Construct the DI container for the given settings.

    Phase 2 note: `user_repository` and `refresh_token_store` are in-memory
    adapters (see ADR-0005). Swapping either for a persistent adapter in a
    later phase means changing only the two lines below that construct
    them — no change to any application service or route.
    """
    user_repository = InMemoryUserRepository()
    refresh_token_store = InMemoryRefreshTokenStore()

    password_hasher = BcryptPasswordHasher()
    token_service = JWTTokenService(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        access_token_ttl=timedelta(minutes=settings.access_token_expire_minutes),
        refresh_token_ttl=timedelta(days=settings.refresh_token_expire_days),
    )

    auth_service = AuthenticationService(
        user_repository=user_repository,
        refresh_token_store=refresh_token_store,
        password_hasher=password_hasher,
        token_service=token_service,
    )
    user_service = UserService(user_repository=user_repository)

    return Container(
        user_repository=user_repository,
        refresh_token_store=refresh_token_store,
        auth_service=auth_service,
        user_service=user_service,
    )


async def ensure_bootstrap_admin(container: Container, settings: Settings) -> None:
    """Ensure a single ADMIN-role user exists, if configured.

    A dev/local convenience (see `Settings.bootstrap_admin_email`): without
    it, a fresh Phase 2 deployment has no way to reach an admin-only
    endpoint, since self-registration always assigns `Role.MEMBER`. No-op if
    either setting is unset, or if a user with that email already exists
    (idempotent — safe to call on every startup).
    """
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    existing = await container.user_repository.get_by_email(settings.bootstrap_admin_email)
    if existing is not None:
        return

    await container.auth_service.register(
        RegisterUserInput(
            email=settings.bootstrap_admin_email,
            password=settings.bootstrap_admin_password,
            full_name="Bootstrap Admin",
        ),
        role=Role.ADMIN,
    )

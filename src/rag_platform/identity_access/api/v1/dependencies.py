"""FastAPI dependencies for the identity_access API.

Everything here is glue: pull the DI container off `app.state`, open a
per-request DB session, build repositories/services from it, extract and
validate the bearer token, enforce a permission. None of it contains
business rules — those live in the application services and domain roles
module this glue calls into.

FastAPI caches a dependency's result for the duration of one request (keyed
by the dependency callable), so even though `get_auth_service` and
`get_user_service` each depend on `get_user_repository`, that repository —
and the `AsyncSession` underneath it — is only constructed once per request
and shared between them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.core.config import get_settings
from rag_platform.di.containers import Container
from rag_platform.identity_access.application.services.auth_service import AuthenticationService
from rag_platform.identity_access.application.services.user_service import UserService
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.exceptions import InsufficientPermissionsError
from rag_platform.identity_access.domain.ports import RefreshTokenStorePort, UserRepositoryPort
from rag_platform.identity_access.domain.roles import Permission, role_has_permission
from rag_platform.identity_access.infrastructure.repositories.postgres_refresh_token_store import (
    PostgresRefreshTokenStore,
)
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
)
from rag_platform.platform.database.dependencies import get_db_session

_settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{_settings.api_v1_prefix}/auth/login")


def get_container(request: Request) -> Container:
    """Retrieve the process-wide DI container from application state.

    Set once in `main.create_app()`. Never constructed per-request.
    """
    container: Container = request.app.state.container
    return container


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRepositoryPort:
    """Build a `UserRepositoryPort` bound to this request's DB session.

    Currently always a `PostgresUserRepository` — see ADR-0006. If a future
    phase needs to swap this per-environment, this is the one function that
    changes.
    """
    return PostgresUserRepository(session)


def get_refresh_token_store(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RefreshTokenStorePort:
    return PostgresRefreshTokenStore(session)


def get_auth_service(
    container: Annotated[Container, Depends(get_container)],
    user_repository: Annotated[UserRepositoryPort, Depends(get_user_repository)],
    refresh_token_store: Annotated[RefreshTokenStorePort, Depends(get_refresh_token_store)],
) -> AuthenticationService:
    return AuthenticationService(
        user_repository=user_repository,
        refresh_token_store=refresh_token_store,
        password_hasher=container.password_hasher,
        token_service=container.token_service,
    )


def get_user_service(
    user_repository: Annotated[UserRepositoryPort, Depends(get_user_repository)],
) -> UserService:
    return UserService(user_repository=user_repository)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: Annotated[AuthenticationService, Depends(get_auth_service)],
) -> User:
    """Resolve the authenticated caller from the bearer access token.

    Any failure (missing/expired/malformed token, unknown or inactive user)
    surfaces as the appropriate `AuthenticationError` subclass, mapped to a
    401 by the shared error-handling middleware — this dependency itself
    never constructs an HTTP response.
    """
    return await auth_service.get_current_user(token)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: Permission) -> Callable[[User], Awaitable[User]]:
    """Build a dependency that requires the caller to hold `permission`.

    Usage: `@router.get(..., dependencies=[Depends(require_permission(Permission.USERS_READ))])`
    Keeps the permission check declarative at the route decorator, so the
    route body stays free of authorization branching.
    """

    async def _check(current_user: CurrentUser) -> User:
        if not role_has_permission(current_user.role, permission):
            raise InsufficientPermissionsError()
        return current_user

    return _check

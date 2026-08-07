"""IdentityAccess domain ports.

Interfaces only. `identity_access/infrastructure/` provides the concrete
implementations; `identity_access/application/` depends on these interfaces,
never on a concrete implementation directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from rag_platform.core.security import TokenClaims, TokenType
    from rag_platform.identity_access.domain.entities import User


class UserRepositoryPort(ABC):
    """Persistence port for `User` entities.

    Phase 2 ships one implementation (`InMemoryUserRepository`). Phase 3
    adds a Postgres-backed implementation of this same interface — no
    application-layer code changes when that happens.
    """

    @abstractmethod
    async def add(self, user: User) -> None: ...

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def update(self, user: User) -> None: ...

    @abstractmethod
    async def list_page(self, *, limit: int, after_id: uuid.UUID | None) -> tuple[list[User], bool]:
        """Return up to `limit` users ordered by id, strictly after `after_id`.

        Returns:
            A tuple of (users, has_more) where `has_more` indicates whether
            additional users exist beyond this page.
        """
        ...


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """Record of a refresh token issued to a user, for revocation tracking."""

    jti: str
    user_id: uuid.UUID
    expires_at: datetime
    revoked: bool = False


class RefreshTokenStorePort(ABC):
    """Tracks issued refresh tokens so they can be revoked (rotation, logout).

    Access tokens are intentionally *not* tracked here — they're short-lived
    and validated by signature + expiry alone (see `TokenServicePort`).
    Only refresh tokens, which are long-lived, need server-side revocation.
    """

    @abstractmethod
    async def store(self, token: IssuedRefreshToken) -> None: ...

    @abstractmethod
    async def get(self, jti: str) -> IssuedRefreshToken | None: ...

    @abstractmethod
    async def revoke(self, jti: str) -> None: ...

    @abstractmethod
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None: ...


class PasswordHasherPort(Protocol):
    """Hashes and verifies passwords. Implemented by a bcrypt adapter."""

    def hash(self, plain_password: str) -> str: ...

    def verify(self, plain_password: str, hashed_password: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class TokenPair:
    """An access/refresh token pair returned to the client after login."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int  # seconds until the access token expires


class TokenServicePort(Protocol):
    """Issues and validates JWTs. Implemented by a PyJWT adapter."""

    def issue_pair(self, user: User) -> tuple[TokenPair, TokenClaims]:
        """Issue a new access/refresh pair for `user`.

        Returns the pair alongside the *refresh* token's claims, so the
        caller can register it with `RefreshTokenStorePort` without
        re-decoding the token it just created.
        """
        ...

    def decode(self, token: str, *, expected_type: TokenType) -> TokenClaims: ...

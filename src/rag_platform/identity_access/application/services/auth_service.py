"""Authentication use cases: register, login, refresh, logout.

Orchestration only — every actual rule (password hashing, token signing,
persistence) is delegated to a port. This class has no framework imports and
no direct dependency on any concrete infrastructure implementation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from rag_platform.core.security import TokenType
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenRevokedError,
    UserAlreadyExistsError,
)
from rag_platform.identity_access.domain.ports import (
    IssuedRefreshToken,
    PasswordHasherPort,
    RefreshTokenStorePort,
    TokenPair,
    TokenServicePort,
    UserRepositoryPort,
)
from rag_platform.identity_access.domain.roles import Role

if TYPE_CHECKING:
    from rag_platform.identity_access.application.dto.auth_dto import LoginInput, RegisterUserInput


class AuthenticationService:
    def __init__(
        self,
        *,
        user_repository: UserRepositoryPort,
        refresh_token_store: RefreshTokenStorePort,
        password_hasher: PasswordHasherPort,
        token_service: TokenServicePort,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_token_store
        self._hasher = password_hasher
        self._tokens = token_service

    async def register(self, data: RegisterUserInput, *, role: Role = Role.MEMBER) -> User:
        """Register a new user.

        Raises:
            UserAlreadyExistsError: if the email is already registered.
        """
        existing = await self._users.get_by_email(data.email)
        if existing is not None:
            raise UserAlreadyExistsError()

        user = User.create(
            email=data.email.strip().lower(),
            hashed_password=self._hasher.hash(data.password),
            full_name=data.full_name,
            role=role,
        )
        await self._users.add(user)
        return user

    async def authenticate(self, data: LoginInput) -> User:
        """Verify credentials and return the matching, active user.

        Raises:
            InvalidCredentialsError: if the email or password doesn't match.
            InactiveUserError: if the account has been deactivated.
        """
        user = await self._users.get_by_email(data.email)
        if user is None or not self._hasher.verify(data.password, user.hashed_password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InactiveUserError()
        return user

    async def issue_tokens(self, user: User) -> TokenPair:
        """Issue a new access/refresh pair and register the refresh token."""
        pair, refresh_claims = self._tokens.issue_pair(user)
        await self._refresh_tokens.store(
            IssuedRefreshToken(
                jti=refresh_claims.jti,
                user_id=user.id,
                expires_at=refresh_claims.expires_at,
            )
        )
        return pair

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a valid, unrevoked refresh token for a new pair.

        Rotation: the presented refresh token is revoked as part of this
        call, so it cannot be reused afterward even if not yet expired.

        Raises:
            InvalidTokenError: if the token is malformed, expired, of the
                wrong type, or its subject no longer refers to a user.
            TokenRevokedError: if the token was already revoked (reuse of a
                rotated-out or logged-out token).
            InactiveUserError: if the user has since been deactivated.
        """
        claims = self._tokens.decode(refresh_token, expected_type=TokenType.REFRESH)

        issued = await self._refresh_tokens.get(claims.jti)
        if issued is None:
            raise InvalidTokenError("Token is unknown to this server.")
        if issued.revoked:
            raise TokenRevokedError()

        user = await self._users.get_by_id(_parse_user_id(claims.subject))
        if user is None:
            raise InvalidTokenError("Token subject does not refer to an existing user.")
        if not user.is_active:
            raise InactiveUserError()

        await self._refresh_tokens.revoke(claims.jti)
        return await self.issue_tokens(user)

    async def logout(self, refresh_token: str) -> None:
        """Revoke a refresh token, ending that session.

        Idempotent: logging out an already-invalid or unknown token is not
        an error — the end state (token unusable) is what the caller wants,
        and it's already true.
        """
        try:
            claims = self._tokens.decode(refresh_token, expected_type=TokenType.REFRESH)
        except InvalidTokenError:
            return
        await self._refresh_tokens.revoke(claims.jti)

    async def get_current_user(self, access_token: str) -> User:
        """Resolve the caller identified by a bearer access token.

        Raises:
            InvalidTokenError: if the token is malformed, expired, or of the
                wrong type, or its subject no longer refers to a user.
            InactiveUserError: if the account has been deactivated.
        """
        claims = self._tokens.decode(access_token, expected_type=TokenType.ACCESS)
        user = await self._users.get_by_id(_parse_user_id(claims.subject))
        if user is None:
            raise InvalidTokenError("Token subject does not refer to an existing user.")
        if not user.is_active:
            raise InactiveUserError()
        return user


def _parse_user_id(subject: str) -> uuid.UUID:
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError("Token subject is not a valid user id.") from exc

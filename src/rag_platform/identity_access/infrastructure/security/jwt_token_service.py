"""JWT-backed implementation of `TokenServicePort`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_platform.core.security import (
    TokenClaims,
    TokenError,
    TokenType,
    decode_token,
    encode_token,
)
from rag_platform.identity_access.domain.exceptions import InvalidTokenError
from rag_platform.identity_access.domain.ports import TokenPair

if TYPE_CHECKING:
    from datetime import timedelta

    from rag_platform.identity_access.domain.entities import User


class JWTTokenService:
    """Implements `TokenServicePort` using the JWT utilities in `core.security`.

    Args:
        secret_key: HMAC signing secret (from `Settings.jwt_secret_key`).
        algorithm: JWT signing algorithm (from `Settings.jwt_algorithm`).
        access_token_ttl: How long an access token remains valid.
        refresh_token_ttl: How long a refresh token remains valid.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        algorithm: str,
        access_token_ttl: timedelta,
        refresh_token_ttl: timedelta,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl

    def issue_pair(self, user: User) -> tuple[TokenPair, TokenClaims]:
        access_token, _ = encode_token(
            subject=str(user.id),
            token_type=TokenType.ACCESS,
            expires_in=self._access_token_ttl,
            secret_key=self._secret_key,
            algorithm=self._algorithm,
        )
        refresh_token, refresh_claims = encode_token(
            subject=str(user.id),
            token_type=TokenType.REFRESH,
            expires_in=self._refresh_token_ttl,
            secret_key=self._secret_key,
            algorithm=self._algorithm,
        )
        pair = TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=int(self._access_token_ttl.total_seconds()),
        )
        return pair, refresh_claims

    def decode(self, token: str, *, expected_type: TokenType) -> TokenClaims:
        try:
            return decode_token(
                token,
                expected_type=expected_type,
                secret_key=self._secret_key,
                algorithm=self._algorithm,
            )
        except TokenError as exc:
            raise InvalidTokenError(str(exc)) from exc

"""Unit tests for the identity_access infrastructure security adapters.

These are thin wrappers over `core.security` — the tests here confirm the
port contract holds (right exception types, right token-type validation)
rather than re-testing the crypto primitives themselves (see
`tests/unit/test_security.py` for that).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from rag_platform.core.security import TokenType
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.exceptions import InvalidTokenError
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.security.jwt_token_service import JWTTokenService
from rag_platform.identity_access.infrastructure.security.password_hasher import (
    BcryptPasswordHasher,
)


@pytest.fixture
def hasher() -> BcryptPasswordHasher:
    return BcryptPasswordHasher()


@pytest.fixture
def token_service() -> JWTTokenService:
    return JWTTokenService(
        secret_key="4i4rlKV4K43qgtpMovZSbreCUSJt9cqvLcIurI9bI30=",
        algorithm="HS256",
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=7),
    )


@pytest.fixture
def user() -> User:
    return User.create(
        email="alice@example.com",
        hashed_password="irrelevant-here",
        full_name="Alice",
        role=Role.MEMBER,
    )


class TestBcryptPasswordHasher:
    def test_hash_then_verify_succeeds(self, hasher: BcryptPasswordHasher) -> None:
        hashed = hasher.hash("my-password")

        assert hasher.verify("my-password", hashed) is True

    def test_verify_fails_for_wrong_password(self, hasher: BcryptPasswordHasher) -> None:
        hashed = hasher.hash("my-password")

        assert hasher.verify("wrong-password", hashed) is False


class TestJWTTokenService:
    def test_issue_pair_returns_working_access_and_refresh_tokens(
        self, token_service: JWTTokenService, user: User
    ) -> None:
        pair, refresh_claims = token_service.issue_pair(user)

        access_claims = token_service.decode(pair.access_token, expected_type=TokenType.ACCESS)
        decoded_refresh_claims = token_service.decode(
            pair.refresh_token, expected_type=TokenType.REFRESH
        )

        assert access_claims.subject == str(user.id)
        assert decoded_refresh_claims.jti == refresh_claims.jti

    def test_issue_pair_sets_bearer_token_type(
        self, token_service: JWTTokenService, user: User
    ) -> None:
        pair, _ = token_service.issue_pair(user)

        assert pair.token_type == "bearer"

    def test_issue_pair_expires_in_matches_configured_ttl(
        self, token_service: JWTTokenService, user: User
    ) -> None:
        pair, _ = token_service.issue_pair(user)

        assert pair.expires_in == 15 * 60

    def test_decode_wraps_token_error_in_domain_exception(
        self, token_service: JWTTokenService
    ) -> None:
        with pytest.raises(InvalidTokenError):
            token_service.decode("not-a-real-token", expected_type=TokenType.ACCESS)

    def test_access_token_rejected_as_refresh(
        self, token_service: JWTTokenService, user: User
    ) -> None:
        pair, _ = token_service.issue_pair(user)

        with pytest.raises(InvalidTokenError):
            token_service.decode(pair.access_token, expected_type=TokenType.REFRESH)

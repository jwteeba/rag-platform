"""Unit tests for `AuthenticationService`.

Uses the real in-memory adapters (not mocks) — they're fast, deterministic,
and exercising the actual `UserRepositoryPort`/`RefreshTokenStorePort`
implementations here is exactly the coverage that matters, since those are
the concrete objects wired together in production for Phase 2.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from rag_platform.identity_access.application.dto.auth_dto import LoginInput, RegisterUserInput
from rag_platform.identity_access.application.services.auth_service import AuthenticationService
from rag_platform.identity_access.domain.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    SessionNotFoundError,
    TokenRevokedError,
    UserAlreadyExistsError,
)
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


@pytest.fixture
def user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def auth_service(user_repository: InMemoryUserRepository) -> AuthenticationService:
    return AuthenticationService(
        user_repository=user_repository,
        refresh_token_store=InMemoryRefreshTokenStore(),
        password_hasher=BcryptPasswordHasher(),
        token_service=JWTTokenService(
            secret_key="4i4rlKV4K43qgtpMovZSbreCUSJt9cqvLcIurI9bI30=",
            algorithm="HS256",
            access_token_ttl=timedelta(minutes=15),
            refresh_token_ttl=timedelta(days=7),
        ),
    )


def _register_input(**overrides: str) -> RegisterUserInput:
    defaults = {"email": "alice@example.com", "password": "AlicePass123", "full_name": "Alice"}
    defaults.update(overrides)
    return RegisterUserInput(**defaults)  # type: ignore[arg-type]


class TestRegister:
    async def test_register_creates_a_member_by_default(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())

        assert user.role is Role.MEMBER
        assert user.email == "alice@example.com"

    async def test_register_can_assign_a_different_role(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input(), role=Role.ADMIN)

        assert user.role is Role.ADMIN

    async def test_register_normalizes_email_case_and_whitespace(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input(email="  Alice@Example.com  "))

        assert user.email == "alice@example.com"

    async def test_register_never_stores_the_plaintext_password(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input(password="AlicePass123"))

        assert user.hashed_password != "AlicePass123"

    async def test_duplicate_email_raises(self, auth_service: AuthenticationService) -> None:
        await auth_service.register(_register_input())

        with pytest.raises(UserAlreadyExistsError):
            await auth_service.register(_register_input())

    async def test_duplicate_email_is_case_insensitive(
        self, auth_service: AuthenticationService
    ) -> None:
        await auth_service.register(_register_input(email="alice@example.com"))

        with pytest.raises(UserAlreadyExistsError):
            await auth_service.register(_register_input(email="ALICE@EXAMPLE.COM"))


class TestAuthenticate:
    async def test_correct_credentials_return_the_user(
        self, auth_service: AuthenticationService
    ) -> None:
        await auth_service.register(_register_input())

        user = await auth_service.authenticate(
            LoginInput(email="alice@example.com", password="AlicePass123")
        )

        assert user.email == "alice@example.com"

    async def test_wrong_password_raises_invalid_credentials(
        self, auth_service: AuthenticationService
    ) -> None:
        await auth_service.register(_register_input())

        with pytest.raises(InvalidCredentialsError):
            await auth_service.authenticate(
                LoginInput(email="alice@example.com", password="WrongPassword")
            )

    async def test_unknown_email_raises_invalid_credentials(
        self, auth_service: AuthenticationService
    ) -> None:
        with pytest.raises(InvalidCredentialsError):
            await auth_service.authenticate(
                LoginInput(email="nobody@example.com", password="AnyPassword123")
            )

    async def test_unknown_email_and_wrong_password_raise_the_same_error(
        self, auth_service: AuthenticationService
    ) -> None:
        """Prevents user enumeration: both cases must be indistinguishable."""
        await auth_service.register(_register_input())

        with pytest.raises(InvalidCredentialsError) as unknown_exc:
            await auth_service.authenticate(LoginInput(email="nobody@example.com", password="x"))
        with pytest.raises(InvalidCredentialsError) as wrong_pw_exc:
            await auth_service.authenticate(
                LoginInput(email="alice@example.com", password="WrongPassword")
            )

        assert unknown_exc.value.message == wrong_pw_exc.value.message


class TestTokenLifecycle:
    async def test_issued_access_token_resolves_back_to_the_user(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())

        pair = await auth_service.issue_tokens(user)
        resolved = await auth_service.get_current_user(pair.access_token)

        assert resolved.id == user.id

    async def test_refresh_returns_a_new_working_pair(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        new_pair = await auth_service.refresh(pair.refresh_token)
        resolved = await auth_service.get_current_user(new_pair.access_token)

        assert resolved.id == user.id
        assert new_pair.refresh_token != pair.refresh_token

    async def test_refresh_revokes_the_presented_token_rotation(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        await auth_service.refresh(pair.refresh_token)

        with pytest.raises(TokenRevokedError):
            await auth_service.refresh(pair.refresh_token)

    async def test_refresh_with_an_access_token_is_rejected(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        with pytest.raises(InvalidTokenError):
            await auth_service.refresh(pair.access_token)

    async def test_get_current_user_with_a_refresh_token_is_rejected(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        with pytest.raises(InvalidTokenError):
            await auth_service.get_current_user(pair.refresh_token)

    async def test_get_current_user_with_garbage_token_raises(
        self, auth_service: AuthenticationService
    ) -> None:
        with pytest.raises(InvalidTokenError):
            await auth_service.get_current_user("not-a-real-token")

    async def test_refresh_with_a_well_formed_but_unregistered_token_raises(
        self, auth_service: AuthenticationService
    ) -> None:
        """A syntactically valid refresh token this server never issued (so
        it's absent from the refresh-token store) must be rejected — not
        just tokens that fail signature/expiry checks."""
        from datetime import timedelta as _timedelta

        from rag_platform.core.security import TokenType as _TokenType
        from rag_platform.core.security import encode_token as _encode_token

        forged_token, _ = _encode_token(
            subject=str((await auth_service.register(_register_input())).id),
            token_type=_TokenType.REFRESH,
            expires_in=_timedelta(minutes=5),
            secret_key="4i4rlKV4K43qgtpMovZSbreCUSJt9cqvLcIurI9bI30=",
            algorithm="HS256",
        )

        with pytest.raises(InvalidTokenError, match="unknown to this server"):
            await auth_service.refresh(forged_token)

    async def test_refresh_for_a_deleted_user_raises(
        self, auth_service: AuthenticationService, user_repository: InMemoryUserRepository
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)
        user_repository._users.pop(user.id)

        with pytest.raises(InvalidTokenError, match="does not refer to an existing user"):
            await auth_service.refresh(pair.refresh_token)

    async def test_refresh_for_a_deactivated_user_raises(
        self, auth_service: AuthenticationService, user_repository: InMemoryUserRepository
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)
        user.deactivate()
        await user_repository.update(user)

        with pytest.raises(InactiveUserError):
            await auth_service.refresh(pair.refresh_token)

    async def test_get_current_user_for_a_deleted_user_raises(
        self, auth_service: AuthenticationService, user_repository: InMemoryUserRepository
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)
        user_repository._users.pop(user.id)

        with pytest.raises(InvalidTokenError, match="does not refer to an existing user"):
            await auth_service.get_current_user(pair.access_token)

    async def test_token_with_malformed_subject_raises(
        self, auth_service: AuthenticationService
    ) -> None:
        from datetime import timedelta as _timedelta

        from rag_platform.core.security import TokenType as _TokenType
        from rag_platform.core.security import encode_token as _encode_token

        malformed_token, _ = _encode_token(
            subject="not-a-uuid",
            token_type=_TokenType.ACCESS,
            expires_in=_timedelta(minutes=5),
            secret_key="4i4rlKV4K43qgtpMovZSbreCUSJt9cqvLcIurI9bI30=",
            algorithm="HS256",
        )

        with pytest.raises(InvalidTokenError, match="not a valid user id"):
            await auth_service.get_current_user(malformed_token)

    async def test_logout_revokes_the_refresh_token(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        await auth_service.logout(pair.refresh_token)

        with pytest.raises(TokenRevokedError):
            await auth_service.refresh(pair.refresh_token)

    async def test_logout_is_idempotent_for_unknown_token(
        self, auth_service: AuthenticationService
    ) -> None:
        # Should not raise.
        await auth_service.logout("not-a-real-token")

    async def test_logout_is_idempotent_when_called_twice(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        await auth_service.logout(pair.refresh_token)
        # Should not raise the second time either.
        await auth_service.logout(pair.refresh_token)


class TestInactiveUser:
    async def test_authenticate_rejects_deactivated_user(
        self, auth_service: AuthenticationService, user_repository: InMemoryUserRepository
    ) -> None:
        user = await auth_service.register(_register_input())
        user.deactivate()
        await user_repository.update(user)

        with pytest.raises(InactiveUserError):
            await auth_service.authenticate(
                LoginInput(email="alice@example.com", password="AlicePass123")
            )

    async def test_get_current_user_rejects_deactivated_user(
        self, auth_service: AuthenticationService, user_repository: InMemoryUserRepository
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)
        user.deactivate()
        await user_repository.update(user)

        with pytest.raises(InactiveUserError):
            await auth_service.get_current_user(pair.access_token)


class TestSessionManagement:
    async def test_list_sessions_empty_for_new_user(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())

        assert await auth_service.list_sessions(user.id) == []

    async def test_list_sessions_reflects_logins(self, auth_service: AuthenticationService) -> None:
        user = await auth_service.register(_register_input())
        await auth_service.issue_tokens(user)
        await auth_service.issue_tokens(user)  # a second "device"

        sessions = await auth_service.list_sessions(user.id)

        assert len(sessions) == 2

    async def test_list_sessions_excludes_revoked(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        await auth_service.revoke_session(user.id, _jti_of(pair.refresh_token))

        assert await auth_service.list_sessions(user.id) == []

    async def test_revoke_session_makes_that_refresh_token_unusable(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)

        await auth_service.revoke_session(user.id, _jti_of(pair.refresh_token))

        with pytest.raises(TokenRevokedError):
            await auth_service.refresh(pair.refresh_token)

    async def test_revoke_session_does_not_affect_other_sessions(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair_a = await auth_service.issue_tokens(user)
        pair_b = await auth_service.issue_tokens(user)

        await auth_service.revoke_session(user.id, _jti_of(pair_a.refresh_token))

        # pair_b should still work.
        await auth_service.refresh(pair_b.refresh_token)

    async def test_revoke_session_of_unknown_jti_raises_session_not_found(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())

        with pytest.raises(SessionNotFoundError):
            await auth_service.revoke_session(user.id, "not-a-real-jti")

    async def test_revoke_session_belonging_to_another_user_raises_session_not_found(
        self, auth_service: AuthenticationService
    ) -> None:
        """Ownership check: can't revoke someone else's session by jti."""
        owner = await auth_service.register(_register_input(email="owner@example.com"))
        attacker = await auth_service.register(_register_input(email="attacker@example.com"))
        pair = await auth_service.issue_tokens(owner)

        with pytest.raises(SessionNotFoundError):
            await auth_service.revoke_session(attacker.id, _jti_of(pair.refresh_token))

    async def test_revoke_session_already_revoked_raises_session_not_found(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair = await auth_service.issue_tokens(user)
        jti = _jti_of(pair.refresh_token)
        await auth_service.revoke_session(user.id, jti)

        with pytest.raises(SessionNotFoundError):
            await auth_service.revoke_session(user.id, jti)

    async def test_revoke_all_sessions_clears_every_session(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())
        pair_a = await auth_service.issue_tokens(user)
        pair_b = await auth_service.issue_tokens(user)

        await auth_service.revoke_all_sessions(user.id)

        assert await auth_service.list_sessions(user.id) == []
        with pytest.raises(TokenRevokedError):
            await auth_service.refresh(pair_a.refresh_token)
        with pytest.raises(TokenRevokedError):
            await auth_service.refresh(pair_b.refresh_token)

    async def test_revoke_all_sessions_with_none_active_does_not_raise(
        self, auth_service: AuthenticationService
    ) -> None:
        user = await auth_service.register(_register_input())

        # Should not raise even with nothing to revoke.
        await auth_service.revoke_all_sessions(user.id)


def _jti_of(refresh_token: str) -> str:
    """Extract the `jti` claim from a refresh token for test setup —
    application code never needs to do this itself (the service methods
    take a session id / jti directly), but tests need it to simulate a
    client presenting one specific session for revocation."""
    import jwt as pyjwt

    return str(pyjwt.decode(refresh_token, options={"verify_signature": False})["jti"])

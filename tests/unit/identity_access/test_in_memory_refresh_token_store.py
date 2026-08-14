"""Unit tests for `InMemoryRefreshTokenStore`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from rag_platform.identity_access.domain.ports import IssuedRefreshToken
from rag_platform.identity_access.infrastructure.repositories.in_memory_refresh_token_store import (
    InMemoryRefreshTokenStore,
)


@pytest.fixture
def store() -> InMemoryRefreshTokenStore:
    return InMemoryRefreshTokenStore()


def _make_token(user_id: uuid.UUID | None = None, **overrides: object) -> IssuedRefreshToken:
    defaults: dict[str, object] = {
        "jti": str(uuid.uuid4()),
        "user_id": user_id or uuid.uuid4(),
        "expires_at": datetime.now(UTC) + timedelta(days=1),
    }
    defaults.update(overrides)
    return IssuedRefreshToken(**defaults)  # type: ignore[arg-type]


class TestStoreAndGet:
    async def test_get_returns_none_for_unknown_jti(self, store: InMemoryRefreshTokenStore) -> None:
        assert await store.get("unknown-jti") is None

    async def test_store_then_get_returns_the_token(self, store: InMemoryRefreshTokenStore) -> None:
        token = _make_token()

        await store.store(token)

        assert await store.get(token.jti) == token

    async def test_new_token_is_not_revoked(self, store: InMemoryRefreshTokenStore) -> None:
        token = _make_token()
        await store.store(token)

        fetched = await store.get(token.jti)

        assert fetched is not None
        assert fetched.revoked is False


class TestRevoke:
    async def test_revoke_marks_the_token_revoked(self, store: InMemoryRefreshTokenStore) -> None:
        token = _make_token()
        await store.store(token)

        await store.revoke(token.jti)

        fetched = await store.get(token.jti)
        assert fetched is not None
        assert fetched.revoked is True

    async def test_revoke_unknown_jti_is_a_no_op(self, store: InMemoryRefreshTokenStore) -> None:
        # Should not raise.
        await store.revoke("unknown-jti")


class TestRevokeAllForUser:
    async def test_revokes_every_token_for_that_user(
        self, store: InMemoryRefreshTokenStore
    ) -> None:
        user_id = uuid.uuid4()
        token_a = _make_token(user_id=user_id)
        token_b = _make_token(user_id=user_id)
        await store.store(token_a)
        await store.store(token_b)

        await store.revoke_all_for_user(user_id)

        fetched_a = await store.get(token_a.jti)
        fetched_b = await store.get(token_b.jti)
        assert fetched_a is not None and fetched_a.revoked is True
        assert fetched_b is not None and fetched_b.revoked is True

    async def test_does_not_revoke_other_users_tokens(
        self, store: InMemoryRefreshTokenStore
    ) -> None:
        user_id = uuid.uuid4()
        other_user_token = _make_token()
        await store.store(other_user_token)

        await store.revoke_all_for_user(user_id)

        fetched = await store.get(other_user_token.jti)
        assert fetched is not None
        assert fetched.revoked is False


class TestListActiveForUser:
    async def test_empty_store_returns_empty_list(self, store: InMemoryRefreshTokenStore) -> None:
        assert await store.list_active_for_user(uuid.uuid4()) == []

    async def test_returns_only_that_users_tokens(self, store: InMemoryRefreshTokenStore) -> None:
        user_id = uuid.uuid4()
        mine = _make_token(user_id=user_id)
        someone_elses = _make_token()
        await store.store(mine)
        await store.store(someone_elses)

        active = await store.list_active_for_user(user_id)

        assert [t.jti for t in active] == [mine.jti]

    async def test_excludes_revoked_tokens(self, store: InMemoryRefreshTokenStore) -> None:
        user_id = uuid.uuid4()
        token = _make_token(user_id=user_id)
        await store.store(token)
        await store.revoke(token.jti)

        assert await store.list_active_for_user(user_id) == []

    async def test_excludes_expired_tokens(self, store: InMemoryRefreshTokenStore) -> None:
        user_id = uuid.uuid4()
        expired = _make_token(user_id=user_id, expires_at=datetime.now(UTC) - timedelta(seconds=1))
        await store.store(expired)

        assert await store.list_active_for_user(user_id) == []

    async def test_includes_multiple_active_sessions(
        self, store: InMemoryRefreshTokenStore
    ) -> None:
        user_id = uuid.uuid4()
        token_a = _make_token(user_id=user_id)
        token_b = _make_token(user_id=user_id)
        await store.store(token_a)
        await store.store(token_b)

        active = await store.list_active_for_user(user_id)

        assert {t.jti for t in active} == {token_a.jti, token_b.jti}

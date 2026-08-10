"""Integration tests for `PostgresRefreshTokenStore`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.ports import IssuedRefreshToken
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.models import UserModel
from rag_platform.identity_access.infrastructure.repositories.postgres_refresh_token_store import (
    PostgresRefreshTokenStore,
)
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
)
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture
async def session(clean_database: None) -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
def store(session: AsyncSession) -> PostgresRefreshTokenStore:
    return PostgresRefreshTokenStore(session)


@pytest.fixture
async def existing_user_id(session: AsyncSession) -> uuid.UUID:
    """A refresh token's `user_id` is a real FK — insert a user row first."""
    user = User.create(
        email="alice@example.com", hashed_password="hashed", full_name="Alice", role=Role.MEMBER
    )
    await PostgresUserRepository(session).add(user)
    await session.commit()
    return user.id


def _make_token(user_id: uuid.UUID, **overrides: object) -> IssuedRefreshToken:
    defaults: dict[str, object] = {
        "jti": str(uuid.uuid4()),
        "user_id": user_id,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
    }
    defaults.update(overrides)
    return IssuedRefreshToken(**defaults)  # type: ignore[arg-type]


class TestStoreAndGet:
    async def test_get_returns_none_for_unknown_jti(self, store: PostgresRefreshTokenStore) -> None:
        assert await store.get("unknown-jti") is None

    async def test_store_then_get_returns_an_equivalent_token(
        self, store: PostgresRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        token = _make_token(existing_user_id)

        await store.store(token)
        await session.commit()

        fetched = await store.get(token.jti)
        assert fetched is not None
        assert fetched.jti == token.jti
        assert fetched.user_id == existing_user_id
        assert fetched.revoked is False


class TestRevoke:
    async def test_revoke_marks_the_token_revoked(
        self, store: PostgresRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()

        await store.revoke(token.jti)
        await session.commit()

        fetched = await store.get(token.jti)
        assert fetched is not None
        assert fetched.revoked is True

    async def test_revoke_unknown_jti_is_a_no_op(self, store: PostgresRefreshTokenStore) -> None:
        # Should not raise.
        await store.revoke("unknown-jti")


class TestRevokeAllForUser:
    async def test_revokes_every_token_for_that_user(
        self, store: PostgresRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        token_a = _make_token(existing_user_id)
        token_b = _make_token(existing_user_id)
        await store.store(token_a)
        await store.store(token_b)
        await session.commit()

        await store.revoke_all_for_user(existing_user_id)
        await session.commit()

        fetched_a = await store.get(token_a.jti)
        fetched_b = await store.get(token_b.jti)
        assert fetched_a is not None and fetched_a.revoked is True
        assert fetched_b is not None and fetched_b.revoked is True

    async def test_cascade_deletes_when_user_is_deleted(
        self, store: PostgresRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        """The FK's `ondelete=CASCADE` — deleting a user cleans up their tokens."""
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()

        await session.execute(delete(UserModel).where(UserModel.id == existing_user_id))
        await session.commit()

        assert await store.get(token.jti) is None

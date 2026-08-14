"""Integration tests for `CachedRefreshTokenStore`.

Wraps a real `PostgresRefreshTokenStore` with a real `CacheService` (real
Redis) — exercises the actual cache-aside behavior described in ADR-0007,
not a mocked approximation of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag_platform.core.cache import CacheService
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.ports import IssuedRefreshToken
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.models import RefreshTokenModel
from rag_platform.identity_access.infrastructure.repositories.cached_refresh_token_store import (
    CachedRefreshTokenStore,
    _cache_key,
)
from rag_platform.identity_access.infrastructure.repositories.postgres_refresh_token_store import (
    PostgresRefreshTokenStore,
)
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
)
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL

TTL_SECONDS = 60


@pytest.fixture
async def session(clean_database: None) -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
async def redis_client(clean_cache: None) -> Redis:
    client: Redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def store(session: AsyncSession, redis_client: Redis) -> CachedRefreshTokenStore:
    return CachedRefreshTokenStore(
        wrapped=PostgresRefreshTokenStore(session),
        cache=CacheService(redis_client),
        ttl_seconds=TTL_SECONDS,
    )


@pytest.fixture
async def existing_user_id(session: AsyncSession) -> uuid.UUID:
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


class TestCacheAsideGet:
    async def test_get_on_a_cold_cache_falls_through_to_postgres(
        self, store: CachedRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()

        fetched = await store.get(token.jti)

        assert fetched is not None
        assert fetched.jti == token.jti

    async def test_get_populates_the_cache_on_a_miss(
        self,
        store: CachedRefreshTokenStore,
        session: AsyncSession,
        redis_client: Redis,
        existing_user_id: uuid.UUID,
    ) -> None:
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()

        await store.get(token.jti)  # first call: cache miss, populates cache

        cached_raw = await redis_client.get(_cache_key(token.jti))
        assert cached_raw is not None

    async def test_get_on_a_warm_cache_matches_postgres_without_needing_a_commit(
        self,
        store: CachedRefreshTokenStore,
        session: AsyncSession,
        existing_user_id: uuid.UUID,
    ) -> None:
        """A second `get()` for the same jti is served from cache — prove
        this by deleting the underlying Postgres row without going through
        the store (bypassing cache invalidation) and confirming the cached
        answer is still returned rather than a fresh (now-missing) lookup."""
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()
        await store.get(token.jti)  # warm the cache

        await session.execute(delete(RefreshTokenModel).where(RefreshTokenModel.jti == token.jti))
        await session.commit()

        # Postgres no longer has this row, but the cache does.
        fetched = await store.get(token.jti)
        assert fetched is not None
        assert fetched.jti == token.jti

    async def test_get_returns_none_for_unknown_jti_and_does_not_cache_it(
        self, store: CachedRefreshTokenStore, redis_client: Redis
    ) -> None:
        result = await store.get("unknown-jti")

        assert result is None
        assert await redis_client.get(_cache_key("unknown-jti")) is None


class TestInvalidationOnMutation:
    async def test_revoke_invalidates_the_cache_entry(
        self,
        store: CachedRefreshTokenStore,
        session: AsyncSession,
        redis_client: Redis,
        existing_user_id: uuid.UUID,
    ) -> None:
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()
        await store.get(token.jti)  # warm the cache
        assert await redis_client.get(_cache_key(token.jti)) is not None

        await store.revoke(token.jti)
        await session.commit()

        assert await redis_client.get(_cache_key(token.jti)) is None

    async def test_get_after_revoke_reflects_the_revocation(
        self, store: CachedRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()
        await store.get(token.jti)  # warm the cache with the not-revoked state

        await store.revoke(token.jti)
        await session.commit()

        fetched = await store.get(token.jti)
        assert fetched is not None
        assert fetched.revoked is True

    async def test_revoke_all_for_user_invalidates_every_cached_session(
        self,
        store: CachedRefreshTokenStore,
        session: AsyncSession,
        redis_client: Redis,
        existing_user_id: uuid.UUID,
    ) -> None:
        token_a = _make_token(existing_user_id)
        token_b = _make_token(existing_user_id)
        await store.store(token_a)
        await store.store(token_b)
        await session.commit()
        await store.get(token_a.jti)  # warm both
        await store.get(token_b.jti)
        assert await redis_client.get(_cache_key(token_a.jti)) is not None
        assert await redis_client.get(_cache_key(token_b.jti)) is not None

        await store.revoke_all_for_user(existing_user_id)
        await session.commit()

        assert await redis_client.get(_cache_key(token_a.jti)) is None
        assert await redis_client.get(_cache_key(token_b.jti)) is None

    async def test_revoke_all_for_user_with_no_active_sessions_does_not_error(
        self, store: CachedRefreshTokenStore, existing_user_id: uuid.UUID
    ) -> None:
        # Should not raise even with nothing to invalidate.
        await store.revoke_all_for_user(existing_user_id)


class TestListActiveForUserIsNotCached:
    async def test_list_active_for_user_delegates_straight_through(
        self, store: CachedRefreshTokenStore, session: AsyncSession, existing_user_id: uuid.UUID
    ) -> None:
        token = _make_token(existing_user_id)
        await store.store(token)
        await session.commit()

        sessions = await store.list_active_for_user(existing_user_id)

        assert len(sessions) == 1
        assert sessions[0].jti == token.jti

"""Unit tests for `rag_platform.core.cache.CacheService`.

Uses a real Redis client (not a mock) — Redis is fast and disposable
enough that a fake would add complexity without adding confidence. Lives
under `tests/integration/`, not `tests/unit/`, because it requires Redis
reachable — consistent with how the Postgres-backed repository tests live
here rather than in `tests/unit/`.
"""

from __future__ import annotations

import pytest
from redis.asyncio import Redis

from rag_platform.core.cache import CacheService
from tests.conftest import TEST_REDIS_URL


@pytest.fixture
async def redis_client(clean_cache: None) -> Redis:
    client: Redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def cache(redis_client: Redis) -> CacheService:
    return CacheService(redis_client)


class TestGetSetJson:
    async def test_get_returns_none_for_missing_key(self, cache: CacheService) -> None:
        assert await cache.get_json("missing-key") is None

    async def test_set_then_get_round_trips_a_dict(self, cache: CacheService) -> None:
        await cache.set_json("a-key", {"hello": "world", "n": 1}, ttl_seconds=30)

        assert await cache.get_json("a-key") == {"hello": "world", "n": 1}

    async def test_set_then_get_round_trips_a_list(self, cache: CacheService) -> None:
        await cache.set_json("a-list", [1, 2, 3], ttl_seconds=30)

        assert await cache.get_json("a-list") == [1, 2, 3]

    async def test_overwriting_a_key_replaces_the_value(self, cache: CacheService) -> None:
        await cache.set_json("a-key", {"v": 1}, ttl_seconds=30)
        await cache.set_json("a-key", {"v": 2}, ttl_seconds=30)

        assert await cache.get_json("a-key") == {"v": 2}

    async def test_value_expires_after_ttl(self, cache: CacheService, redis_client: Redis) -> None:
        await cache.set_json("a-key", {"v": 1}, ttl_seconds=30)

        ttl = await redis_client.ttl("a-key")
        assert 0 < ttl <= 30


class TestDelete:
    async def test_delete_removes_the_key(self, cache: CacheService) -> None:
        await cache.set_json("a-key", {"v": 1}, ttl_seconds=30)

        await cache.delete("a-key")

        assert await cache.get_json("a-key") is None

    async def test_delete_multiple_keys_at_once(self, cache: CacheService) -> None:
        await cache.set_json("key-a", 1, ttl_seconds=30)
        await cache.set_json("key-b", 2, ttl_seconds=30)

        await cache.delete("key-a", "key-b")

        assert await cache.get_json("key-a") is None
        assert await cache.get_json("key-b") is None

    async def test_delete_of_missing_key_is_a_no_op(self, cache: CacheService) -> None:
        # Should not raise.
        await cache.delete("never-existed")

    async def test_delete_with_no_keys_is_a_no_op(self, cache: CacheService) -> None:
        # Should not raise, and should not call Redis with an empty DEL.
        await cache.delete()

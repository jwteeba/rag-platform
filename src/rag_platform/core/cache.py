"""Redis client construction and a generic cache-aside helper.

Framework-light (the `redis` library only, no FastAPI) by design, per the
Shared/Core layering rule — mirrors `core/db.py`'s role for Postgres.

Unlike `core/db.py`'s per-request `AsyncSession`, a single `redis.asyncio.Redis`
client is safe to share as a process-wide singleton: it multiplexes
commands over an internal connection pool itself, so there's no equivalent
"one session per request" concern. `Container` holds one instance for the
life of the process (see `di/containers.py`).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from redis.asyncio import ConnectionPool, Redis

if TYPE_CHECKING:
    from rag_platform.core.config import Settings


def build_redis_client(settings: Settings) -> Redis:
    """Create the async Redis client from application settings."""
    pool = ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,
    )
    return Redis(connection_pool=pool)


class CacheService:
    """A small cache-aside helper over a Redis client.

    Deliberately minimal — JSON-serializable values only, TTL required on
    every write. Not a generic Redis wrapper exposing every command; call
    sites that need more than get/set/delete of a JSON-serializable value
    should use the injected `Redis` client directly rather than growing this
    class into an unfocused catch-all.
    """

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get_json(self, key: str) -> Any | None:
        """Return the deserialized value for `key`, or `None` on a miss.

        A `None` return is ambiguous between "not cached" and "cached value
        was JSON `null`" — no current caller stores `null`, so this is
        acceptable; a caller that needs to distinguish the two should use
        the Redis client directly instead.
        """
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        """Cache `value` under `key`, expiring after `ttl_seconds`."""
        await self._client.set(key, json.dumps(value), ex=ttl_seconds)

    async def delete(self, *keys: str) -> None:
        """Remove one or more keys from the cache. Missing keys are a no-op."""
        if keys:
            await self._client.delete(*keys)

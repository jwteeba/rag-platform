"""Redis cache-aside layer in front of a `RefreshTokenStorePort`.

Postgres (`PostgresRefreshTokenStore`) remains the source of truth — this
class never stores data Postgres doesn't also have.

Refresh tokens in this application
are single-use — `AuthenticationService.refresh()` and `.revoke_session()`
both call `get()` immediately followed by `revoke()` on the same jti, in
the same request. That means a *sequential* repeat read of an already-used
token rarely happens (it's revoked before anyone could read it again), so
this cache-aside layer isn't the "avoid N redundant DB hits per token"
story a naive reading might suggest. What it does provide:

1. **Concurrent/duplicate requests on the same still-valid token** — e.g. a
   client retrying a flaky `/auth/refresh` call, or a double-click — can
   have their `get()` served from cache rather than racing each other
   against Postgres.
2. **The reusable pattern itself.** `CacheService` and this cache-aside
   shape (check cache → fall through on miss → cache the result → write-
   through invalidation on mutation) is exactly what Phase 0's planned
   caching consumers (embedding cache, LLM response cache, etc., in later
   phases) will reuse. This is the first, concrete, tested example of that
   pattern in the codebase — see ADR-0007.
"""

from __future__ import annotations

import uuid as uuid_module
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rag_platform.identity_access.domain.ports import IssuedRefreshToken, RefreshTokenStorePort

if TYPE_CHECKING:
    import uuid

    from rag_platform.core.cache import CacheService

_CACHE_KEY_PREFIX = "identity_access:refresh_token"


def _cache_key(jti: str) -> str:
    return f"{_CACHE_KEY_PREFIX}:{jti}"


def _to_cache_dict(token: IssuedRefreshToken) -> dict[str, object]:
    data = asdict(token)
    data["user_id"] = str(token.user_id)
    data["expires_at"] = token.expires_at.isoformat()
    return data


def _from_cache_dict(data: dict[str, object]) -> IssuedRefreshToken:
    return IssuedRefreshToken(
        jti=str(data["jti"]),
        user_id=uuid_module.UUID(str(data["user_id"])),
        expires_at=datetime.fromisoformat(str(data["expires_at"])).astimezone(UTC),
        revoked=bool(data["revoked"]),
    )


class CachedRefreshTokenStore(RefreshTokenStorePort):
    def __init__(
        self,
        *,
        wrapped: RefreshTokenStorePort,
        cache: CacheService,
        ttl_seconds: int,
    ) -> None:
        self._wrapped = wrapped
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def store(self, token: IssuedRefreshToken) -> None:
        await self._wrapped.store(token)
        # No stale entry to invalidate for a brand-new jti in the normal
        # case, but clearing defensively costs nothing and removes any
        # possibility of a race with a concurrent `get()` on the same jti.
        await self._cache.delete(_cache_key(token.jti))

    async def get(self, jti: str) -> IssuedRefreshToken | None:
        cached = await self._cache.get_json(_cache_key(jti))
        if cached is not None:
            return _from_cache_dict(cached)

        token = await self._wrapped.get(jti)
        if token is not None:
            await self._cache.set_json(
                _cache_key(jti), _to_cache_dict(token), ttl_seconds=self._ttl_seconds
            )
        return token

    async def revoke(self, jti: str) -> None:
        await self._wrapped.revoke(jti)
        await self._cache.delete(_cache_key(jti))

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        # Must invalidate every cached entry for this user, not just
        # whichever one triggered this call — an active session's cached
        # "not revoked" entry would otherwise keep reading as valid for up
        # to `ttl_seconds` after a "log out everywhere".
        active = await self._wrapped.list_active_for_user(user_id)
        await self._wrapped.revoke_all_for_user(user_id)
        if active:
            await self._cache.delete(*(_cache_key(token.jti) for token in active))

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[IssuedRefreshToken]:
        return await self._wrapped.list_active_for_user(user_id)

"""In-memory implementation of `RefreshTokenStorePort`.

Same rationale as `InMemoryUserRepository`: a complete, tested Phase 2
adapter. Not what the running application uses as of Phase 3 (Postgres,
see `postgres_refresh_token_store.py`) or Phase 4 (a Redis cache-aside
layer in front of Postgres, see `cached_refresh_token_store.py`) — still
shipped and unit-tested behind the same port, per ADR-0005.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rag_platform.identity_access.domain.ports import IssuedRefreshToken, RefreshTokenStorePort

if TYPE_CHECKING:
    import uuid


class InMemoryRefreshTokenStore(RefreshTokenStorePort):
    def __init__(self) -> None:
        self._tokens: dict[str, IssuedRefreshToken] = {}
        self._lock = asyncio.Lock()

    async def store(self, token: IssuedRefreshToken) -> None:
        async with self._lock:
            self._tokens[token.jti] = token

    async def get(self, jti: str) -> IssuedRefreshToken | None:
        async with self._lock:
            return self._tokens.get(jti)

    async def revoke(self, jti: str) -> None:
        async with self._lock:
            existing = self._tokens.get(jti)
            if existing is not None:
                self._tokens[jti] = IssuedRefreshToken(
                    jti=existing.jti,
                    user_id=existing.user_id,
                    expires_at=existing.expires_at,
                    revoked=True,
                )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        async with self._lock:
            for jti, token in list(self._tokens.items()):
                if token.user_id == user_id and not token.revoked:
                    self._tokens[jti] = IssuedRefreshToken(
                        jti=token.jti,
                        user_id=token.user_id,
                        expires_at=token.expires_at,
                        revoked=True,
                    )

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[IssuedRefreshToken]:
        now = datetime.now(UTC)
        async with self._lock:
            return [
                token
                for token in self._tokens.values()
                if token.user_id == user_id and not token.revoked and token.expires_at > now
            ]

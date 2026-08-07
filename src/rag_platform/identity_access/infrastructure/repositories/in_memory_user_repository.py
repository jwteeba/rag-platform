"""In-memory implementation of `UserRepositoryPort`.

Phase 2 has no database yet (that's Phase 3), so this adapter backs the
service with a process-local, lock-protected dict instead. It is a complete,
correct, tested implementation of the port — not a stub — and is intended to
be swapped for a Postgres-backed adapter in Phase 3 without any change to
`identity_access/application/` or `identity_access/domain/`. See ADR-0005.

Data does not survive a process restart. That's an accepted, documented
limitation of Phase 2, not an oversight.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rag_platform.identity_access.domain.ports import UserRepositoryPort

if TYPE_CHECKING:
    import uuid

    from rag_platform.identity_access.domain.entities import User


class InMemoryUserRepository(UserRepositoryPort):
    def __init__(self) -> None:
        self._users: dict[uuid.UUID, User] = {}
        self._lock = asyncio.Lock()

    async def add(self, user: User) -> None:
        async with self._lock:
            self._users[user.id] = user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        async with self._lock:
            return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        async with self._lock:
            for user in self._users.values():
                if user.email.lower() == normalized:
                    return user
        return None

    async def update(self, user: User) -> None:
        async with self._lock:
            self._users[user.id] = user

    async def list_page(self, *, limit: int, after_id: uuid.UUID | None) -> tuple[list[User], bool]:
        async with self._lock:
            ordered = sorted(self._users.values(), key=lambda u: u.id)

        if after_id is not None:
            ordered = [u for u in ordered if u.id > after_id]

        page = ordered[:limit]
        has_more = len(ordered) > limit
        return page, has_more

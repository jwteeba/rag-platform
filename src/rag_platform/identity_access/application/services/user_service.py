"""User management use cases: profile lookup/update, admin listing/updates.

Permission checks (e.g. "only an admin may list all users") are *not*
performed here — they're enforced by a reusable FastAPI dependency in
`identity_access/api/v1/dependencies.py`, applied at the route level. This
service assumes the caller has already been authorized for the operation
it's asked to perform; it only enforces rules that are true regardless of
who's calling (e.g. "the target user must exist").
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from rag_platform.core.pagination import Page, decode_cursor, encode_cursor
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.exceptions import UserNotFoundError

if TYPE_CHECKING:
    from rag_platform.identity_access.domain.ports import UserRepositoryPort
    from rag_platform.identity_access.domain.roles import Role


class UserService:
    def __init__(self, *, user_repository: UserRepositoryPort) -> None:
        self._users = user_repository

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    async def update_profile(self, user_id: uuid.UUID, *, full_name: str) -> User:
        """Self-service profile update — any authenticated user, own record only.

        Ownership (that `user_id` matches the caller) is enforced by the API
        layer, which only ever calls this with the caller's own id.
        """
        user = await self.get_by_id(user_id)
        user.rename(full_name)
        await self._users.update(user)
        return user

    async def list_users(self, *, limit: int, cursor: str | None) -> Page[User]:
        after_id = uuid.UUID(decode_cursor(cursor)) if cursor else None
        users, has_more = await self._users.list_page(limit=limit, after_id=after_id)
        next_cursor = encode_cursor(str(users[-1].id)) if has_more and users else None
        return Page[User](items=users, has_more=has_more, next_cursor=next_cursor)

    async def update_role_and_status(
        self,
        user_id: uuid.UUID,
        *,
        role: Role | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Admin update of a target user's role and/or active status."""
        user = await self.get_by_id(user_id)
        if role is not None:
            user.change_role(role)
        if is_active is not None:
            if is_active:
                user.activate()
            else:
                user.deactivate()
        await self._users.update(user)
        return user

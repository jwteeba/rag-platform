"""Postgres-backed implementation of `UserRepositoryPort`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.ports import UserRepositoryPort
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.models import UserModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        hashed_password=model.hashed_password,
        full_name=model.full_name,
        role=Role(model.role),
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _apply_domain_to_model(user: User, model: UserModel) -> None:
    model.id = user.id
    model.email = user.email
    model.hashed_password = user.hashed_password
    model.full_name = user.full_name
    model.role = user.role.value
    model.is_active = user.is_active


class PostgresUserRepository(UserRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        model = UserModel()
        _apply_domain_to_model(user, model)
        self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _to_domain(model) if model is not None else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(func.lower(UserModel.email) == email.strip().lower())
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return _to_domain(model) if model is not None else None

    async def update(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            # The port contract assumes `update` is only called for a user
            # that was previously loaded via this repository — mirrors what
            # every application-layer caller (`UserService`,
            # `AuthenticationService`) already does (get-then-mutate-then-
            # update). Surfacing a clear error here beats a silent no-op.
            raise ValueError(f"Cannot update user {user.id}: no such row.")
        _apply_domain_to_model(user, model)
        await self._session.flush()

    async def list_page(self, *, limit: int, after_id: uuid.UUID | None) -> tuple[list[User], bool]:
        stmt = select(UserModel).order_by(UserModel.id).limit(limit + 1)
        if after_id is not None:
            stmt = stmt.where(UserModel.id > after_id)

        result = await self._session.execute(stmt)
        models = list(result.scalars().all())

        has_more = len(models) > limit
        page = models[:limit]
        return [_to_domain(m) for m in page], has_more

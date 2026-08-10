"""Postgres-backed implementation of `RefreshTokenStorePort`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import update

from rag_platform.identity_access.domain.ports import IssuedRefreshToken, RefreshTokenStorePort
from rag_platform.identity_access.infrastructure.models import RefreshTokenModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: RefreshTokenModel) -> IssuedRefreshToken:
    return IssuedRefreshToken(
        jti=model.jti,
        user_id=model.user_id,
        expires_at=model.expires_at,
        revoked=model.revoked,
    )


class PostgresRefreshTokenStore(RefreshTokenStorePort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(self, token: IssuedRefreshToken) -> None:
        model = RefreshTokenModel(
            jti=token.jti,
            user_id=token.user_id,
            expires_at=token.expires_at,
            revoked=token.revoked,
        )
        self._session.add(model)
        await self._session.flush()

    async def get(self, jti: str) -> IssuedRefreshToken | None:
        model = await self._session.get(RefreshTokenModel, jti)
        return _to_domain(model) if model is not None else None

    async def revoke(self, jti: str) -> None:
        stmt = update(RefreshTokenModel).where(RefreshTokenModel.jti == jti).values(revoked=True)
        await self._session.execute(stmt)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = (
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id, RefreshTokenModel.revoked.is_(False))
            .values(revoked=True)
        )
        await self._session.execute(stmt)
        await self._session.flush()

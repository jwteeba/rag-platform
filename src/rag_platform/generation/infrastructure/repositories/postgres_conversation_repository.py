"""Postgres conversation and message repositories."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from rag_platform.generation.domain.entities import Conversation, Message
from rag_platform.generation.infrastructure.models import ConversationModel, MessageModel

if TYPE_CHECKING:
    import builtins

    from sqlalchemy.ext.asyncio import AsyncSession


class PostgresConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            ConversationModel(
                id=conversation.id, owner_id=conversation.owner_id, title=conversation.title
            )
        )
        await self._session.flush()

    async def get(self, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> Conversation | None:
        row = await self._session.scalar(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id, ConversationModel.owner_id == owner_id
            )
        )
        return Conversation(row.id, row.owner_id, row.title, row.created_at) if row else None

    async def list(
        self, owner_id: uuid.UUID, limit: int, cursor: str | None = None
    ) -> list[Conversation]:
        query = select(ConversationModel).where(ConversationModel.owner_id == owner_id)
        if cursor:
            query = query.where(ConversationModel.id < uuid.UUID(cursor))
        rows = (
            await self._session.scalars(query.order_by(ConversationModel.id.desc()).limit(limit))
        ).all()
        return [Conversation(r.id, r.owner_id, r.title, r.created_at) for r in rows]

    async def delete(self, conversation_id: uuid.UUID) -> None:
        row = await self._session.get(ConversationModel, conversation_id)
        if row:
            await self._session.delete(row)
            await self._session.flush()


class PostgresMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: Message) -> None:
        self._session.add(
            MessageModel(
                id=message.id,
                conversation_id=message.conversation_id,
                role=message.role,
                content=message.content,
                token_count=message.token_count,
            )
        )
        await self._session.flush()

    async def list(
        self, conversation_id: uuid.UUID, limit: int, cursor: str | None = None
    ) -> list[Message]:
        query = select(MessageModel).where(MessageModel.conversation_id == conversation_id)
        if cursor:
            query = query.where(MessageModel.id > uuid.UUID(cursor))
        rows = (await self._session.scalars(query.order_by(MessageModel.id).limit(limit))).all()
        return [
            Message(r.id, r.conversation_id, r.role, r.content, r.token_count, r.created_at)
            for r in rows
        ]

    async def list_recent(self, conversation_id: uuid.UUID, limit: int) -> builtins.list[Message]:
        rows = (
            await self._session.scalars(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.id.desc())
                .limit(limit)
            )
        ).all()
        return [
            Message(r.id, r.conversation_id, r.role, r.content, r.token_count, r.created_at)
            for r in reversed(rows)
        ]

    async def list_all(self, conversation_id: uuid.UUID) -> builtins.list[Message]:
        rows = (
            await self._session.scalars(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.id)
            )
        ).all()
        return [
            Message(r.id, r.conversation_id, r.role, r.content, r.token_count, r.created_at)
            for r in rows
        ]

"""Authenticated conversation and answer generation endpoints."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.generation.api.v1.dependencies import get_generation_service
from rag_platform.generation.api.v1.schemas import (
    ConversationMessageRequest,
    ConversationStartRequest,
)
from rag_platform.generation.application.services.generation_service import GenerationService
from rag_platform.generation.domain.entities import Message
from rag_platform.generation.domain.exceptions import ConversationNotFoundError
from rag_platform.generation.infrastructure.repositories.postgres_conversation_repository import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from rag_platform.identity_access.api.v1.dependencies import CurrentUser
from rag_platform.platform.database.dependencies import get_db_session

router = APIRouter(tags=["conversations"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
ServiceDep = Annotated[GenerationService, Depends(get_generation_service)]


def _message(m: Message) -> dict[str, object]:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "role": m.role,
        "content": m.content,
        "token_count": m.token_count,
        "created_at": m.created_at,
    }


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def start_conversation(
    body: ConversationStartRequest, user: CurrentUser, service: ServiceDep
) -> dict[str, object]:
    conversation, result = await service.start(body.query.strip(), limit=body.limit)
    return {
        "conversation_id": conversation.id,
        "answer": result.answer,
        "source_documents": result.source_documents,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
    }


@router.post("/conversations/{conversation_id}/messages")
async def continue_conversation(
    conversation_id: uuid.UUID,
    body: ConversationMessageRequest,
    user: CurrentUser,
    service: ServiceDep,
) -> dict[str, object]:
    result = await service.continue_conversation(
        conversation_id, body.query.strip(), limit=body.limit
    )
    return {
        "conversation_id": conversation_id,
        "answer": result.answer,
        "source_documents": result.source_documents,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
    }


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: uuid.UUID,
    body: ConversationMessageRequest,
    user: CurrentUser,
    service: ServiceDep,
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for chunk in service.stream(conversation_id, body.query.strip(), limit=body.limit):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.get("/conversations")
async def list_conversations(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> dict[str, object]:
    items = await PostgresConversationRepository(session).list(user.id, limit + 1, cursor)
    more = len(items) > limit
    items = items[:limit]
    return {
        "items": items,
        "has_more": more,
        "next_cursor": str(items[-1].id) if more and items else None,
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> dict[str, object]:
    conversation = await PostgresConversationRepository(session).get(conversation_id, user.id)
    if conversation is None:
        raise ConversationNotFoundError()
    messages = await PostgresMessageRepository(session).list_all(conversation_id)
    return {"conversation": conversation, "messages": [_message(m) for m in messages]}


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> dict[str, object]:
    if await PostgresConversationRepository(session).get(conversation_id, user.id) is None:
        raise ConversationNotFoundError()
    messages = await PostgresMessageRepository(session).list(conversation_id, limit + 1, cursor)
    more = len(messages) > limit
    messages = messages[:limit]
    return {
        "items": [_message(m) for m in messages],
        "has_more": more,
        "next_cursor": str(messages[-1].id) if more and messages else None,
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> None:
    repo = PostgresConversationRepository(session)
    if await repo.get(conversation_id, user.id) is None:
        raise ConversationNotFoundError()
    await repo.delete(conversation_id)

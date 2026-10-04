from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from rag_platform.generation.application.services.generation_service import GenerationService
from rag_platform.generation.domain.entities import (
    AssembledPrompt,
    Conversation,
    GenerationResult,
    Message,
)
from rag_platform.generation.domain.exceptions import ContextWindowExceededError


class FakeCounter:
    def count(self, text: str) -> int:
        return len(text.split())


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> tuple[str, int, int]:
        self.calls.append(messages)
        return "A canned answer", 4, 3

    async def stream(self, messages: list[dict[str, str]], **kwargs) -> AsyncIterator[str]:
        yield "A "
        yield "streamed answer"


class FakeConversations:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, Conversation] = {}

    async def add(self, conversation: Conversation) -> None:
        self.items[conversation.id] = conversation

    async def get(self, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> Conversation | None:
        item = self.items.get(conversation_id)
        return item if item and item.owner_id == owner_id else None


class FakeMessages:
    def __init__(self) -> None:
        self.items: list[Message] = []

    async def add(self, message: Message) -> None:
        self.items.append(message)

    async def list_recent(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        return [m for m in self.items if m.conversation_id == conversation_id][-limit:]


class FakeRetrieval:
    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]

    async def search(self, query: str, owner_id: uuid.UUID, *, limit: int, query_vector=None):
        return []


class FakeAssembler:
    async def assemble(self, query: str, chunks: list[object]) -> AssembledPrompt:
        return AssembledPrompt("system", [], query, 2, f"Question: {query}")


class FakeSemanticCache:
    def __init__(self, result) -> None:
        self.result = result

    def lookup(self, owner_id, query_vector, *, namespace, similarity_threshold):
        return self.result

    def store(self, owner_id, query_vector, result, *, namespace):
        self.result = result


@pytest.mark.asyncio
async def test_generation_persists_turn_and_reuses_prior_history() -> None:
    owner = uuid.uuid4()
    conversations, messages, llm = FakeConversations(), FakeMessages(), FakeLLM()
    service = GenerationService(
        conversations,
        messages,
        llm,
        FakeRetrieval(),
        FakeAssembler(),
        FakeCounter(),
        owner_id=owner,
        model="fake",
        temperature=0,
        max_tokens=20,
        max_context_tokens=100,
        history_limit=10,
    )

    conversation, initial = await service.start("first question")
    second = await service.continue_conversation(conversation.id, "follow up")

    assert initial.answer == second.answer == "A canned answer"
    assert len(messages.items) == 4
    assert llm.calls[1][1]["content"] == "first question"
    assert llm.calls[1][2]["content"] == "A canned answer"
    assert llm.calls[1][-1]["content"] == "Question: follow up"


@pytest.mark.asyncio
async def test_generation_rejects_history_that_exceeds_budget() -> None:
    owner, conversation_id = uuid.uuid4(), uuid.uuid4()
    conversations, messages = FakeConversations(), FakeMessages()
    conversations.items[conversation_id] = Conversation(
        conversation_id, owner, "long chat", datetime.now(UTC)
    )
    await messages.add(
        Message(uuid.uuid4(), conversation_id, "user", "too much history", 50, datetime.now(UTC))
    )
    service = GenerationService(
        conversations,
        messages,
        FakeLLM(),
        FakeRetrieval(),
        FakeAssembler(),
        FakeCounter(),
        owner_id=owner,
        model="fake",
        temperature=0,
        max_tokens=20,
        max_context_tokens=10,
        history_limit=10,
    )

    with pytest.raises(ContextWindowExceededError):
        await service.continue_conversation(conversation_id, "question")


@pytest.mark.asyncio
async def test_stream_yields_incremental_chunks_and_persists_completed_turn() -> None:
    owner, conversation_id = uuid.uuid4(), uuid.uuid4()
    conversations, messages = FakeConversations(), FakeMessages()
    conversations.items[conversation_id] = Conversation(
        conversation_id, owner, "stream", datetime.now(UTC)
    )
    service = GenerationService(
        conversations,
        messages,
        FakeLLM(),
        FakeRetrieval(),
        FakeAssembler(),
        FakeCounter(),
        owner_id=owner,
        model="fake",
        temperature=0,
        max_tokens=20,
        max_context_tokens=100,
        history_limit=10,
    )

    chunks = [chunk async for chunk in service.stream(conversation_id, "question")]

    assert chunks == ["A ", "streamed answer"]
    assert [message.role for message in messages.items] == ["user", "assistant"]
    assert messages.items[-1].content == "A streamed answer"


@pytest.mark.asyncio
async def test_semantic_cache_returns_same_result_without_calling_llm() -> None:
    owner = uuid.uuid4()
    conversations, messages, llm = FakeConversations(), FakeMessages(), FakeLLM()
    cached = GenerationResult("cached response", [], 9, 4, 13)
    service = GenerationService(
        conversations,
        messages,
        llm,
        FakeRetrieval(),
        FakeAssembler(),
        FakeCounter(),
        owner_id=owner,
        model="fake",
        temperature=0,
        max_tokens=20,
        max_context_tokens=100,
        history_limit=10,
        semantic_cache=FakeSemanticCache(cached),
    )

    _, result = await service.start("similar question")

    assert result == cached
    assert llm.calls == []
    assert [message.content for message in messages.items] == [
        "similar question",
        "cached response",
    ]

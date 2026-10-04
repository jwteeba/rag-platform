"""Generation domain ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import builtins
    import uuid
    from collections.abc import AsyncIterator

    from rag_platform.generation.domain.entities import (
        Conversation,
        GenerationResult,
        Message,
        PromptTemplate,
    )


@runtime_checkable
class PromptTemplateRepositoryPort(Protocol):
    async def add(self, template: PromptTemplate) -> None: ...
    async def get_by_id(self, template_id: uuid.UUID) -> PromptTemplate | None: ...
    async def get_by_name(self, name: str) -> PromptTemplate | None: ...
    async def list_all(self) -> list[PromptTemplate]: ...
    async def update(self, template: PromptTemplate) -> None: ...
    async def delete(self, template_id: uuid.UUID) -> None: ...


@runtime_checkable
class TokenCounterPort(Protocol):
    def count(self, text: str) -> int:
        """Return the number of tokens in `text` for the configured model."""
        ...


@runtime_checkable
class LLMPort(Protocol):
    async def complete(
        self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int
    ) -> tuple[str, int, int]: ...
    def stream(
        self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]: ...


@runtime_checkable
class ConversationRepositoryPort(Protocol):
    async def add(self, conversation: Conversation) -> None: ...
    async def get(self, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> Conversation | None: ...
    async def list(
        self, owner_id: uuid.UUID, limit: int, cursor: str | None = None
    ) -> list[Conversation]: ...
    async def delete(self, conversation_id: uuid.UUID) -> None: ...


@runtime_checkable
class MessageRepositoryPort(Protocol):
    async def add(self, message: Message) -> None: ...
    async def list(
        self, conversation_id: uuid.UUID, limit: int, cursor: str | None = None
    ) -> list[Message]: ...
    async def list_recent(
        self, conversation_id: uuid.UUID, limit: int
    ) -> builtins.list[Message]: ...
    async def list_all(self, conversation_id: uuid.UUID) -> builtins.list[Message]: ...


@runtime_checkable
class SemanticResponseCachePort(Protocol):
    def lookup(
        self,
        owner_id: uuid.UUID,
        query_vector: list[float],
        *,
        namespace: str,
        similarity_threshold: float,
    ) -> GenerationResult | None: ...

    def store(
        self,
        owner_id: uuid.UUID,
        query_vector: list[float],
        result: GenerationResult,
        *,
        namespace: str,
    ) -> None: ...

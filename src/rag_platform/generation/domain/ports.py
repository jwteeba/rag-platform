"""Generation domain ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid

    from rag_platform.generation.domain.entities import PromptTemplate


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

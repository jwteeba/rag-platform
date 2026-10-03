"""Generation domain entities."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from rag_platform.core.ids import generate_uuid7


@dataclass(slots=True)
class PromptTemplate:
    id: uuid.UUID
    name: str
    system_prompt: str
    user_template: str
    model_target: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        name: str,
        system_prompt: str,
        user_template: str,
        model_target: str,
    ) -> PromptTemplate:
        now = datetime.now(UTC)
        return cls(
            id=generate_uuid7(),
            name=name,
            system_prompt=system_prompt,
            user_template=user_template,
            model_target=model_target,
            created_at=now,
            updated_at=now,
        )


@dataclass(slots=True)
class AssembledPrompt:
    """A fully assembled prompt ready to send to an LLM.

    `context_chunks` is the ordered list of (filename, chunk_index, content)
    tuples that were fitted within the context window — the LLM can use these
    for source attribution. `token_count` is the pre-flight tiktoken count of
    system_prompt + rendered context + user_query combined.
    """

    system_prompt: str
    context_chunks: list[tuple[str, int, str]]  # (filename, chunk_index, content)
    user_query: str
    token_count: int
    rendered_user_prompt: str = ""

    @property
    def rendered_context(self) -> str:
        """Format context chunks for insertion into the user template."""
        parts = []
        for filename, chunk_index, content in self.context_chunks:
            parts.append(f"[Source: {filename}, chunk {chunk_index}]\n{content}")
        return "\n\n".join(parts)


@dataclass(slots=True)
class Conversation:
    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    created_at: datetime

    @classmethod
    def create(cls, owner_id: uuid.UUID, title: str) -> Conversation:
        return cls(generate_uuid7(), owner_id, title[:200], datetime.now(UTC))


@dataclass(slots=True)
class Message:
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    token_count: int
    created_at: datetime

    @classmethod
    def create(
        cls, conversation_id: uuid.UUID, role: str, content: str, token_count: int = 0
    ) -> Message:
        return cls(generate_uuid7(), conversation_id, role, content, token_count, datetime.now(UTC))


@dataclass(slots=True)
class GenerationResult:
    answer: str
    source_documents: list[dict[str, str | int]]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

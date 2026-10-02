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

    @property
    def rendered_context(self) -> str:
        """Format context chunks for insertion into the user template."""
        parts = []
        for filename, chunk_index, content in self.context_chunks:
            parts.append(f"[Source: {filename}, chunk {chunk_index}]\n{content}")
        return "\n\n".join(parts)

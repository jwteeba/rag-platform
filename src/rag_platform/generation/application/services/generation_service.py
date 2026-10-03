"""Conversation orchestration for retrieval augmented answer generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_platform.generation.domain.entities import Conversation, GenerationResult, Message
from rag_platform.generation.domain.exceptions import (
    ContextWindowExceededError,
    ConversationNotFoundError,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from rag_platform.generation.application.services.prompt_assembly_service import (
        PromptAssemblyService,
    )
    from rag_platform.generation.domain.ports import (
        ConversationRepositoryPort,
        LLMPort,
        MessageRepositoryPort,
        TokenCounterPort,
    )
    from rag_platform.retrieval.application.services.retrieval_service import RetrievalService


class GenerationService:
    def __init__(
        self,
        conversations: ConversationRepositoryPort,
        messages: MessageRepositoryPort,
        llm: LLMPort,
        retrieval: RetrievalService,
        assembler: PromptAssemblyService,
        counter: TokenCounterPort,
        *,
        owner_id: uuid.UUID,
        model: str,
        temperature: float,
        max_tokens: int,
        max_context_tokens: int,
        history_limit: int,
    ) -> None:
        self.conversations, self.messages, self.llm = conversations, messages, llm
        self.retrieval, self.assembler, self.counter = retrieval, assembler, counter
        self.owner_id, self.model = owner_id, model
        self.temperature, self.max_tokens = temperature, max_tokens
        self.max_context_tokens, self.history_limit = max_context_tokens, history_limit

    async def start(self, query: str, *, limit: int = 5) -> tuple[Conversation, GenerationResult]:
        conversation = Conversation.create(self.owner_id, query.strip()[:200])
        await self.conversations.add(conversation)
        result = await self._generate(conversation, query, limit=limit, history=[])
        return conversation, result

    async def continue_conversation(
        self, conversation_id: uuid.UUID, query: str, *, limit: int = 5
    ) -> GenerationResult:
        conversation = await self.conversations.get(conversation_id, self.owner_id)
        if conversation is None:
            raise ConversationNotFoundError()
        history = await self.messages.list_recent(conversation_id, self.history_limit)
        return await self._generate(conversation, query, limit=limit, history=history)

    async def _generate(
        self, conversation: Conversation, query: str, *, limit: int, history: list[Message]
    ) -> GenerationResult:
        chunks = await self.retrieval.search(query, self.owner_id, limit=limit)
        prompt = await self.assembler.assemble(query, chunks)
        history_tokens = sum(m.token_count or self.counter.count(m.content) for m in history)
        prompt_tokens = self.counter.count(prompt.system_prompt) + self.counter.count(
            prompt.rendered_user_prompt
        )
        if history_tokens + prompt_tokens + self.max_tokens > self.max_context_tokens:
            raise ContextWindowExceededError(
                "Conversation history, retrieved context, query, and response exceed the "
                "configured token budget."
            )
        llm_messages = [{"role": "system", "content": prompt.system_prompt}]
        llm_messages.extend(
            {"role": m.role, "content": m.content}
            for m in history
            if m.role in {"user", "assistant"}
        )
        llm_messages.append({"role": "user", "content": prompt.rendered_user_prompt})
        answer, used_prompt, completion = await self.llm.complete(
            llm_messages, model=self.model, temperature=self.temperature, max_tokens=self.max_tokens
        )
        await self.messages.add(
            Message.create(conversation.id, "user", query, self.counter.count(query))
        )
        await self.messages.add(Message.create(conversation.id, "assistant", answer, completion))
        sources: list[dict[str, str | int]] = [
            {"filename": fn, "chunk_index": idx} for fn, idx, _ in prompt.context_chunks
        ]
        return GenerationResult(
            answer,
            sources,
            used_prompt or prompt_tokens,
            completion,
            (used_prompt or prompt_tokens) + completion,
        )

    async def stream(
        self, conversation_id: uuid.UUID, query: str, *, limit: int = 5
    ) -> AsyncIterator[str]:
        conversation = await self.conversations.get(conversation_id, self.owner_id)
        if conversation is None:
            raise ConversationNotFoundError()
        history = await self.messages.list_recent(conversation_id, self.history_limit)
        chunks = await self.retrieval.search(query, self.owner_id, limit=limit)
        prompt = await self.assembler.assemble(query, chunks)
        history_tokens = sum(m.token_count or self.counter.count(m.content) for m in history)
        prompt_tokens = self.counter.count(prompt.system_prompt) + self.counter.count(
            prompt.rendered_user_prompt
        )
        if history_tokens + prompt_tokens + self.max_tokens > self.max_context_tokens:
            raise ContextWindowExceededError()
        llm_messages = [{"role": "system", "content": prompt.system_prompt}]
        llm_messages.extend(
            {"role": m.role, "content": m.content}
            for m in history
            if m.role in {"user", "assistant"}
        )
        llm_messages.append({"role": "user", "content": prompt.rendered_user_prompt})
        parts: list[str] = []
        async for chunk in self.llm.stream(
            llm_messages, model=self.model, temperature=self.temperature, max_tokens=self.max_tokens
        ):
            parts.append(chunk)
            yield chunk
        answer = "".join(parts)
        await self.messages.add(
            Message.create(conversation.id, "user", query, self.counter.count(query))
        )
        await self.messages.add(
            Message.create(conversation.id, "assistant", answer, self.counter.count(answer))
        )

"""Conversation orchestration for retrieval augmented answer generation."""

from __future__ import annotations

import hashlib
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
        SemanticResponseCachePort,
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
        semantic_cache: SemanticResponseCachePort | None = None,
        cache_namespace: str = "",
        cache_similarity_threshold: float = 0.97,
    ) -> None:
        self.conversations, self.messages, self.llm = conversations, messages, llm
        self.retrieval, self.assembler, self.counter = retrieval, assembler, counter
        self.owner_id, self.model = owner_id, model
        self.temperature, self.max_tokens = temperature, max_tokens
        self.max_context_tokens, self.history_limit = max_context_tokens, history_limit
        self.semantic_cache = semantic_cache
        self.cache_namespace = cache_namespace
        self.cache_similarity_threshold = cache_similarity_threshold

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
        query_vector = self.retrieval.embed_query(query)
        namespace = self._turn_cache_namespace(history, limit)
        cached = await self._lookup_cached(query_vector, namespace)
        if cached is not None:
            await self._persist_turn(conversation, query, cached)
            return cached

        chunks = await self.retrieval.search(
            query, self.owner_id, limit=limit, query_vector=query_vector
        )
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
        sources: list[dict[str, str | int]] = [
            {"filename": fn, "chunk_index": idx} for fn, idx, _ in prompt.context_chunks
        ]
        result = GenerationResult(
            answer,
            sources,
            used_prompt or prompt_tokens,
            completion,
            (used_prompt or prompt_tokens) + completion,
        )
        await self._store_cached(query_vector, namespace, result)
        await self._persist_turn(conversation, query, result)
        return result

    async def stream(
        self, conversation_id: uuid.UUID, query: str, *, limit: int = 5
    ) -> AsyncIterator[str]:
        conversation = await self.conversations.get(conversation_id, self.owner_id)
        if conversation is None:
            raise ConversationNotFoundError()
        history = await self.messages.list_recent(conversation_id, self.history_limit)
        query_vector = self.retrieval.embed_query(query)
        namespace = self._turn_cache_namespace(history, limit)
        cached = await self._lookup_cached(query_vector, namespace)
        if cached is not None:
            await self._persist_turn(conversation, query, cached)
            for offset in range(0, len(cached.answer), 128):
                yield cached.answer[offset : offset + 128]
            return

        chunks = await self.retrieval.search(
            query, self.owner_id, limit=limit, query_vector=query_vector
        )
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
        prompt_tokens = self.counter.count(prompt.system_prompt) + self.counter.count(
            prompt.rendered_user_prompt
        )
        result = GenerationResult(
            answer=answer,
            source_documents=[
                {"filename": fn, "chunk_index": idx} for fn, idx, _ in prompt.context_chunks
            ],
            prompt_tokens=prompt_tokens,
            completion_tokens=self.counter.count(answer),
            total_tokens=prompt_tokens + self.counter.count(answer),
        )
        await self._store_cached(query_vector, namespace, result)
        await self._persist_turn(conversation, query, result)

    def _turn_cache_namespace(self, history: list[Message], limit: int) -> str:
        history_key = "\n".join(f"{m.role}:{m.content}" for m in history)
        history_digest = hashlib.sha256(history_key.encode()).hexdigest()[:16]
        return f"{self.cache_namespace}:{history_digest}:limit:{limit}"

    async def _lookup_cached(
        self, query_vector: list[float], namespace: str
    ) -> GenerationResult | None:
        if self.semantic_cache is None:
            return None
        return self.semantic_cache.lookup(
            self.owner_id,
            query_vector,
            namespace=namespace,
            similarity_threshold=self.cache_similarity_threshold,
        )

    async def _store_cached(
        self, query_vector: list[float], namespace: str, result: GenerationResult
    ) -> None:
        if self.semantic_cache is not None:
            self.semantic_cache.store(
                self.owner_id,
                query_vector,
                result,
                namespace=namespace,
            )

    async def _persist_turn(
        self, conversation: Conversation, query: str, result: GenerationResult
    ) -> None:
        await self.messages.add(
            Message.create(conversation.id, "user", query, self.counter.count(query))
        )
        await self.messages.add(
            Message.create(conversation.id, "assistant", result.answer, result.completion_tokens)
        )

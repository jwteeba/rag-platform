"""FastAPI dependencies for the generation API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.generation.application.services.generation_service import GenerationService
from rag_platform.generation.application.services.prompt_assembly_service import (
    PromptAssemblyService,
)
from rag_platform.generation.domain.ports import LLMPort
from rag_platform.generation.infrastructure.cache.semantic_response_cache import (
    SemanticResponseCache,
)
from rag_platform.generation.infrastructure.llm.anthropic_llm_adapter import AnthropicLLMAdapter
from rag_platform.generation.infrastructure.llm.openai_llm_adapter import OpenAILLMAdapter
from rag_platform.generation.infrastructure.repositories.postgres_conversation_repository import (
    PostgresConversationRepository,
    PostgresMessageRepository,
)
from rag_platform.generation.infrastructure.repositories.postgres_prompt_template_repository import (  # noqa: E501
    PostgresPromptTemplateRepository,
)
from rag_platform.generation.infrastructure.token_counter.tiktoken_counter import TiktokenCounter
from rag_platform.identity_access.api.v1.dependencies import CurrentUser
from rag_platform.platform.database.dependencies import get_db_session
from rag_platform.retrieval.api.v1.dependencies import get_retrieval_service
from rag_platform.retrieval.application.services.retrieval_service import RetrievalService


def get_prompt_assembly_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PromptAssemblyService:
    settings = request.app.state.settings
    return PromptAssemblyService(
        template_repo=PostgresPromptTemplateRepository(session),
        token_counter=TiktokenCounter(settings.tiktoken_model),
        max_context_tokens=settings.max_context_tokens,
        default_template_name=settings.default_prompt_template_name,
    )


def get_template_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PostgresPromptTemplateRepository:
    return PostgresPromptTemplateRepository(session)


def get_generation_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user: CurrentUser,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> GenerationService:
    settings = request.app.state.settings
    llm: LLMPort = (
        AnthropicLLMAdapter(settings.anthropic_api_key)
        if settings.llm_provider == "anthropic"
        else OpenAILLMAdapter(settings.openai_api_key)
    )
    counter = TiktokenCounter(settings.tiktoken_model)
    assembler = PromptAssemblyService(
        PostgresPromptTemplateRepository(session),
        counter,
        settings.max_context_tokens,
        settings.default_prompt_template_name,
    )
    return GenerationService(
        PostgresConversationRepository(session),
        PostgresMessageRepository(session),
        llm,
        retrieval,
        assembler,
        counter,
        owner_id=user.id,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        max_context_tokens=settings.max_context_tokens,
        history_limit=settings.max_conversation_history_messages,
        semantic_cache=SemanticResponseCache(
            request.app.state.container.cache_sync_client,
            ttl_seconds=settings.llm_cache_ttl_seconds,
            enabled=settings.llm_cache_enabled,
        ),
        cache_namespace=(
            f"{settings.llm_provider}:{settings.llm_model}:"
            f"{settings.llm_temperature}:{settings.llm_max_tokens}:"
            f"{settings.embedding_provider}:{settings.embedding_model}:"
            f"{settings.default_prompt_template_name}:{settings.max_context_tokens}:"
            f"{settings.search_score_threshold}"
        ),
        cache_similarity_threshold=settings.llm_cache_similarity_threshold,
    )

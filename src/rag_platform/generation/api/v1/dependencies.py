"""FastAPI dependencies for the generation API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_platform.generation.application.services.prompt_assembly_service import (
    PromptAssemblyService,
)
from rag_platform.generation.infrastructure.repositories.postgres_prompt_template_repository import (  # noqa: E501
    PostgresPromptTemplateRepository,
)
from rag_platform.generation.infrastructure.token_counter.tiktoken_counter import TiktokenCounter
from rag_platform.platform.database.dependencies import get_db_session


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

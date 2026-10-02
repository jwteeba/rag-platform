"""Generation API router — prompt template CRUD + context assembly."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from rag_platform.core.exceptions import ValidationError
from rag_platform.generation.api.v1.dependencies import (
    get_prompt_assembly_service,
    get_template_repo,
)
from rag_platform.generation.api.v1.schemas import (
    AssembledPromptResponse,
    AssembleRequest,
    PromptTemplateCreateRequest,
    PromptTemplateListResponse,
    PromptTemplateResponse,
    PromptTemplateUpdateRequest,
    SourceChunk,
)
from rag_platform.generation.application.services.prompt_assembly_service import (
    PromptAssemblyService,
)
from rag_platform.generation.domain.entities import PromptTemplate
from rag_platform.generation.domain.exceptions import TemplateNotFoundError
from rag_platform.generation.infrastructure.repositories.postgres_prompt_template_repository import (  # noqa: E501
    PostgresPromptTemplateRepository,
)
from rag_platform.identity_access.api.v1.dependencies import CurrentUser, require_permission
from rag_platform.identity_access.domain.roles import Permission
from rag_platform.retrieval.domain.entities import SearchResult

router = APIRouter(prefix="/prompt-templates", tags=["generation"])

TemplateRepoDep = Annotated[PostgresPromptTemplateRepository, Depends(get_template_repo)]
AssemblyServiceDep = Annotated[PromptAssemblyService, Depends(get_prompt_assembly_service)]


def _to_response(t: PromptTemplate) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=t.id,
        name=t.name,
        system_prompt=t.system_prompt,
        user_template=t.user_template,
        model_target=t.model_target,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.post(
    "",
    response_model=PromptTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a prompt template",
    dependencies=[Depends(require_permission(Permission.PROMPT_TEMPLATES_MANAGE))],
)
async def create_template(
    body: PromptTemplateCreateRequest,
    repo: TemplateRepoDep,
) -> PromptTemplateResponse:
    existing = await repo.get_by_name(body.name)
    if existing is not None:
        from rag_platform.core.exceptions import ConflictError

        raise ConflictError(f"A template named '{body.name}' already exists.")
    template = PromptTemplate.create(
        name=body.name,
        system_prompt=body.system_prompt,
        user_template=body.user_template,
        model_target=body.model_target,
    )
    await repo.add(template)
    return _to_response(template)


@router.get(
    "",
    response_model=PromptTemplateListResponse,
    summary="List all prompt templates",
    dependencies=[Depends(require_permission(Permission.PROMPT_TEMPLATES_MANAGE))],
)
async def list_templates(repo: TemplateRepoDep) -> PromptTemplateListResponse:
    templates = await repo.list_all()
    return PromptTemplateListResponse(items=[_to_response(t) for t in templates])


@router.get(
    "/{template_id}",
    response_model=PromptTemplateResponse,
    summary="Get a prompt template by id",
    dependencies=[Depends(require_permission(Permission.PROMPT_TEMPLATES_MANAGE))],
)
async def get_template(template_id: uuid.UUID, repo: TemplateRepoDep) -> PromptTemplateResponse:
    template = await repo.get_by_id(template_id)
    if template is None:
        raise TemplateNotFoundError()
    return _to_response(template)


@router.patch(
    "/{template_id}",
    response_model=PromptTemplateResponse,
    summary="Update a prompt template",
    dependencies=[Depends(require_permission(Permission.PROMPT_TEMPLATES_MANAGE))],
)
async def update_template(
    template_id: uuid.UUID,
    body: PromptTemplateUpdateRequest,
    repo: TemplateRepoDep,
) -> PromptTemplateResponse:
    if all(
        v is None for v in [body.name, body.system_prompt, body.user_template, body.model_target]
    ):
        raise ValidationError("At least one field must be provided.")
    template = await repo.get_by_id(template_id)
    if template is None:
        raise TemplateNotFoundError()
    if body.name is not None:
        template.name = body.name
    if body.system_prompt is not None:
        template.system_prompt = body.system_prompt
    if body.user_template is not None:
        template.user_template = body.user_template
    if body.model_target is not None:
        template.model_target = body.model_target
    await repo.update(template)
    return _to_response(template)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a prompt template",
    dependencies=[Depends(require_permission(Permission.PROMPT_TEMPLATES_MANAGE))],
)
async def delete_template(template_id: uuid.UUID, repo: TemplateRepoDep) -> None:
    template = await repo.get_by_id(template_id)
    if template is None:
        raise TemplateNotFoundError()
    await repo.delete(template_id)


@router.post(
    "/assemble",
    response_model=AssembledPromptResponse,
    summary="Assemble a prompt from ranked retrieval chunks",
)
async def assemble_prompt(
    body: AssembleRequest,
    _current_user: CurrentUser,
    service: AssemblyServiceDep,
) -> AssembledPromptResponse:
    chunks = [
        SearchResult(
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            filename=c.filename,
            content=c.content,
            score=c.score,
            chunk_index=c.chunk_index,
        )
        for c in body.chunks
    ]
    assembled = await service.assemble(body.query, chunks, template_id=body.template_id)
    return AssembledPromptResponse(
        system_prompt=assembled.system_prompt,
        rendered_context=assembled.rendered_context,
        user_query=assembled.user_query,
        token_count=assembled.token_count,
        source_chunks=[
            SourceChunk(filename=fn, chunk_index=idx) for fn, idx, _ in assembled.context_chunks
        ],
    )

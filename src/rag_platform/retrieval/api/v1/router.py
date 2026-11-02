"""Retrieval router — POST /search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from rag_platform.identity_access.api.v1.dependencies import CurrentUser, require_permission
from rag_platform.identity_access.domain.roles import Permission
from rag_platform.retrieval.api.v1.dependencies import get_retrieval_service
from rag_platform.retrieval.api.v1.schemas import (
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
)
from rag_platform.retrieval.application.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/search", tags=["retrieval"])

RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]


@router.post(
    "",
    response_model=SearchResponse,
    summary="Semantic search over indexed documents",
    dependencies=[Depends(require_permission(Permission.SEARCH))],
)
async def search(
    body: SearchRequest,
    current_user: CurrentUser,
    service: RetrievalServiceDep,
    request: Request,
) -> SearchResponse:
    results = await service.search(
        body.query,
        current_user.id,
        limit=body.limit,
        document_ids=body.document_ids,
        path=request.url.path,
    )
    return SearchResponse(
        results=[
            SearchResultResponse(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                filename=r.filename,
                content=r.content,
                score=r.score,
                chunk_index=r.chunk_index,
            )
            for r in results
        ]
    )

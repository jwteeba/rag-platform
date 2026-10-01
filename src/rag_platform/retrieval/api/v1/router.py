"""Retrieval router — POST /search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from rag_platform.identity_access.api.v1.dependencies import CurrentUser
from rag_platform.retrieval.api.v1.dependencies import get_retrieval_service
from rag_platform.retrieval.api.v1.schemas import (
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
)
from rag_platform.retrieval.application.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/search", tags=["retrieval"])

RetrievalServiceDep = Annotated[RetrievalService, Depends(get_retrieval_service)]


@router.post("", response_model=SearchResponse, summary="Semantic search over indexed documents")
async def search(
    body: SearchRequest,
    current_user: CurrentUser,
    service: RetrievalServiceDep,
) -> SearchResponse:
    results = await service.search(
        body.query,
        current_user.id,
        limit=body.limit,
        document_ids=body.document_ids,
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

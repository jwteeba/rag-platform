"""Document endpoints.

Thin per the architecture rules: parse request, call one service method,
map result to response schema. No business logic here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile, status
from fastapi.responses import RedirectResponse

from rag_platform.core.pagination import InvalidCursorError, decode_cursor, encode_cursor
from rag_platform.document_management.api.v1.dependencies import get_document_service
from rag_platform.document_management.api.v1.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DownloadUrlResponse,
)
from rag_platform.document_management.application.dto.document_dto import UploadDocumentInput
from rag_platform.document_management.application.services.document_service import DocumentService
from rag_platform.identity_access.api.v1.dependencies import CurrentUser

router = APIRouter(prefix="/documents", tags=["documents"])

DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
async def upload_document(
    file: UploadFile,
    current_user: CurrentUser,
    service: DocumentServiceDep,
) -> DocumentResponse:
    data = await file.read()
    document = await service.upload(
        UploadDocumentInput(
            owner_id=current_user.id,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents owned by the current user",
)
async def list_documents(
    current_user: CurrentUser,
    service: DocumentServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> DocumentListResponse:
    after_id: uuid.UUID | None = None
    if cursor is not None:
        try:
            raw = decode_cursor(cursor)
            after_id = uuid.UUID(raw)
        except (InvalidCursorError, ValueError):
            pass

    documents, has_more = await service.list_for_user(
        current_user.id, limit=limit, after_id=after_id
    )
    next_cursor: str | None = None
    if has_more and documents:
        next_cursor = encode_cursor(str(documents[-1].id))

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in documents],
        has_more=has_more,
        next_cursor=next_cursor,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
)
async def get_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    service: DocumentServiceDep,
) -> DocumentResponse:
    document = await service.get(document_id, requester_id=current_user.id)
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}/download",
    summary="Download a document (307 redirect to presigned URL)",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
)
async def download_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    service: DocumentServiceDep,
) -> RedirectResponse:
    url = await service.get_download_url(document_id, requester_id=current_user.id)
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/{document_id}/download-url",
    response_model=DownloadUrlResponse,
    summary="Get a presigned download URL (JSON)",
)
async def get_download_url(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    service: DocumentServiceDep,
) -> DownloadUrlResponse:
    url = await service.get_download_url(document_id, requester_id=current_user.id)
    return DownloadUrlResponse(url=url)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a document",
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: CurrentUser,
    service: DocumentServiceDep,
) -> None:
    await service.delete(document_id, requester_id=current_user.id)

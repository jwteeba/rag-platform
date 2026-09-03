"""Postgres-backed implementation of `DocumentRepositoryPort`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from rag_platform.document_management.domain.entities import Document, DocumentStatus
from rag_platform.document_management.domain.ports import DocumentRepositoryPort
from rag_platform.document_management.infrastructure.models import DocumentModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: DocumentModel) -> Document:
    return Document(
        id=model.id,
        owner_id=model.owner_id,
        filename=model.filename,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
        storage_key=model.storage_key,
        status=DocumentStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class PostgresDocumentRepository(DocumentRepositoryPort):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> None:
        model = DocumentModel(
            id=document.id,
            owner_id=document.owner_id,
            filename=document.filename,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            storage_key=document.storage_key,
            status=document.status.value,
        )
        self._session.add(model)
        await self._session.flush()

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model is not None else None

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, after_id: uuid.UUID | None
    ) -> tuple[list[Document], bool]:
        stmt = (
            select(DocumentModel)
            .where(DocumentModel.owner_id == owner_id)
            .order_by(DocumentModel.id)
            .limit(limit + 1)
        )
        if after_id is not None:
            stmt = stmt.where(DocumentModel.id > after_id)
        result = await self._session.execute(stmt)
        models = list(result.scalars().all())
        has_more = len(models) > limit
        return [_to_domain(m) for m in models[:limit]], has_more

    async def delete(self, document_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

    async def set_status(self, document_id: uuid.UUID, status: DocumentStatus) -> None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if model is not None:
            model.status = status.value
            await self._session.flush()

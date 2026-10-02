"""Postgres-backed implementation of PromptTemplateRepositoryPort."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from rag_platform.generation.domain.entities import PromptTemplate
from rag_platform.generation.infrastructure.models import PromptTemplateModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: PromptTemplateModel) -> PromptTemplate:
    return PromptTemplate(
        id=model.id,
        name=model.name,
        system_prompt=model.system_prompt,
        user_template=model.user_template,
        model_target=model.model_target,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class PostgresPromptTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, template: PromptTemplate) -> None:
        self._session.add(
            PromptTemplateModel(
                id=template.id,
                name=template.name,
                system_prompt=template.system_prompt,
                user_template=template.user_template,
                model_target=template.model_target,
            )
        )
        await self._session.flush()

    async def get_by_id(self, template_id: uuid.UUID) -> PromptTemplate | None:
        result = await self._session.execute(
            select(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def get_by_name(self, name: str) -> PromptTemplate | None:
        result = await self._session.execute(
            select(PromptTemplateModel).where(PromptTemplateModel.name == name)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model else None

    async def list_all(self) -> list[PromptTemplate]:
        result = await self._session.execute(
            select(PromptTemplateModel).order_by(PromptTemplateModel.name)
        )
        return [_to_domain(m) for m in result.scalars().all()]

    async def update(self, template: PromptTemplate) -> None:
        result = await self._session.execute(
            select(PromptTemplateModel).where(PromptTemplateModel.id == template.id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError(f"Cannot update template {template.id}: no such row.")
        model.name = template.name
        model.system_prompt = template.system_prompt
        model.user_template = template.user_template
        model.model_target = template.model_target
        await self._session.flush()

    async def delete(self, template_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(PromptTemplateModel).where(PromptTemplateModel.id == template_id)
        )
        model = result.scalar_one_or_none()
        if model is not None:
            await self._session.delete(model)
            await self._session.flush()

"""Integration tests for PostgresPromptTemplateRepository."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag_platform.generation.domain.entities import PromptTemplate
from rag_platform.generation.infrastructure.repositories.postgres_prompt_template_repository import (  # noqa: E501
    PostgresPromptTemplateRepository,
)
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture
async def session(clean_database: None) -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
def repo(session: AsyncSession) -> PostgresPromptTemplateRepository:
    return PostgresPromptTemplateRepository(session)


def _make_template(name: str = "test-template") -> PromptTemplate:
    return PromptTemplate.create(
        name=name,
        system_prompt="You are helpful.",
        user_template="Context:\n{context}\n\nQuestion: {query}\n\nAnswer:",
        model_target="gpt-4o",
    )


class TestAddAndGet:
    async def test_get_by_id_returns_none_for_unknown(
        self, repo: PostgresPromptTemplateRepository
    ) -> None:
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_get_by_name_returns_none_for_unknown(
        self, repo: PostgresPromptTemplateRepository
    ) -> None:
        assert await repo.get_by_name("nonexistent") is None

    async def test_add_then_get_by_id(
        self, repo: PostgresPromptTemplateRepository, session: AsyncSession
    ) -> None:
        template = _make_template()
        await repo.add(template)
        await session.commit()

        found = await repo.get_by_id(template.id)
        assert found is not None
        assert found.id == template.id
        assert found.name == template.name
        assert found.system_prompt == template.system_prompt

    async def test_add_then_get_by_name(
        self, repo: PostgresPromptTemplateRepository, session: AsyncSession
    ) -> None:
        template = _make_template(name="my-template")
        await repo.add(template)
        await session.commit()

        found = await repo.get_by_name("my-template")
        assert found is not None
        assert found.id == template.id


class TestListAll:
    async def test_empty_returns_empty(self, repo: PostgresPromptTemplateRepository) -> None:
        assert await repo.list_all() == []

    async def test_returns_all_templates_ordered_by_name(
        self, repo: PostgresPromptTemplateRepository, session: AsyncSession
    ) -> None:
        await repo.add(_make_template("zzz"))
        await repo.add(_make_template("aaa"))
        await session.commit()

        templates = await repo.list_all()
        assert [t.name for t in templates] == ["aaa", "zzz"]


class TestUpdate:
    async def test_update_persists_changes(
        self, repo: PostgresPromptTemplateRepository, session: AsyncSession
    ) -> None:
        template = _make_template()
        await repo.add(template)
        await session.commit()

        template.system_prompt = "Updated system prompt."
        await repo.update(template)
        await session.commit()

        found = await repo.get_by_id(template.id)
        assert found is not None
        assert found.system_prompt == "Updated system prompt."


class TestDelete:
    async def test_delete_removes_template(
        self, repo: PostgresPromptTemplateRepository, session: AsyncSession
    ) -> None:
        template = _make_template()
        await repo.add(template)
        await session.commit()

        await repo.delete(template.id)
        await session.commit()

        assert await repo.get_by_id(template.id) is None

    async def test_delete_unknown_id_is_noop(self, repo: PostgresPromptTemplateRepository) -> None:
        await repo.delete(uuid.uuid4())  # must not raise

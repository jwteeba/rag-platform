"""Integration tests for `PostgresDocumentRepository`."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag_platform.document_management.domain.entities import Chunk, Document, DocumentStatus
from rag_platform.document_management.infrastructure.repositories.postgres_chunk_repository import (
    PostgresChunkRepository,
)
from rag_platform.document_management.infrastructure.repositories.postgres_document_repository import (  # noqa: E501
    PostgresDocumentRepository,
)
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.postgres_user_repository import (
    PostgresUserRepository,
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
def repo(session: AsyncSession) -> PostgresDocumentRepository:
    return PostgresDocumentRepository(session)


async def _make_user(session: AsyncSession) -> User:
    """Insert a real user row to satisfy the documents FK constraint."""
    user = User.create(
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="hashed",
        full_name="Test",
        role=Role.MEMBER,
    )
    user_repo = PostgresUserRepository(session)
    await user_repo.add(user)
    await session.flush()
    return user


def _make_doc(owner_id: uuid.UUID, **overrides: object) -> Document:
    defaults: dict[str, object] = {
        "owner_id": owner_id,
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
    }
    defaults.update(overrides)
    return Document.create(**defaults)  # type: ignore[arg-type]


class TestAddAndGetById:
    async def test_get_by_id_returns_none_for_unknown(
        self, repo: PostgresDocumentRepository
    ) -> None:
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_add_then_get_returns_equivalent(
        self, repo: PostgresDocumentRepository, session: AsyncSession
    ) -> None:
        user = await _make_user(session)
        doc = _make_doc(user.id)
        await repo.add(doc)
        await session.commit()

        found = await repo.get_by_id(doc.id)
        assert found is not None
        assert found.id == doc.id
        assert found.filename == doc.filename
        assert found.storage_key == doc.storage_key

    async def test_survives_a_new_session(
        self, repo: PostgresDocumentRepository, session: AsyncSession
    ) -> None:
        user = await _make_user(session)
        doc = _make_doc(user.id)
        await repo.add(doc)
        await session.commit()

        engine = create_async_engine(TEST_DATABASE_URL)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as other_session:
            other_repo = PostgresDocumentRepository(other_session)
            found = await other_repo.get_by_id(doc.id)
            assert found is not None
            assert found.id == doc.id
        await engine.dispose()


class TestListForOwner:
    async def test_empty_returns_empty(self, repo: PostgresDocumentRepository) -> None:
        docs, has_more = await repo.list_for_owner(uuid.uuid4(), limit=10, after_id=None)
        assert docs == []
        assert has_more is False

    async def test_only_returns_own_documents(
        self, repo: PostgresDocumentRepository, session: AsyncSession
    ) -> None:
        owner = await _make_user(session)
        other = await _make_user(session)
        await repo.add(_make_doc(owner.id))
        await repo.add(_make_doc(other.id))
        await session.commit()

        docs, _ = await repo.list_for_owner(owner.id, limit=10, after_id=None)
        assert len(docs) == 1
        assert docs[0].owner_id == owner.id

    async def test_respects_limit(
        self, repo: PostgresDocumentRepository, session: AsyncSession
    ) -> None:
        owner = await _make_user(session)
        for _ in range(3):
            await repo.add(_make_doc(owner.id))
        await session.commit()

        docs, has_more = await repo.list_for_owner(owner.id, limit=2, after_id=None)
        assert len(docs) == 2
        assert has_more is True


class TestDelete:
    async def test_delete_removes_row(
        self, repo: PostgresDocumentRepository, session: AsyncSession
    ) -> None:
        user = await _make_user(session)
        doc = _make_doc(user.id)
        await repo.add(doc)
        await session.commit()

        await repo.delete(doc.id)
        await session.commit()

        assert await repo.get_by_id(doc.id) is None

    async def test_delete_unknown_id_is_noop(self, repo: PostgresDocumentRepository) -> None:
        await repo.delete(uuid.uuid4())  # must not raise


class TestDocumentStatus:
    async def test_set_status_persists(
        self, repo: PostgresDocumentRepository, session: AsyncSession
    ) -> None:
        user = await _make_user(session)
        document = _make_doc(user.id)
        await repo.add(document)
        await repo.set_status(document.id, DocumentStatus.READY)
        await session.commit()

        found = await repo.get_by_id(document.id)
        assert found is not None
        assert found.status is DocumentStatus.READY


class TestPostgresChunkRepository:
    async def test_replace_and_list_chunks(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        document = _make_doc(user.id)
        documents = PostgresDocumentRepository(session)
        await documents.add(document)
        repository = PostgresChunkRepository(session)
        chunks = [
            Chunk.create(
                document_id=document.id, content="first chunk", chunk_index=0, token_count=2
            ),
            Chunk.create(
                document_id=document.id, content="second chunk", chunk_index=1, token_count=2
            ),
        ]

        await repository.replace_for_document(document.id, chunks)
        await session.commit()

        found = await repository.list_for_document(document.id)
        assert [chunk.content for chunk in found] == ["first chunk", "second chunk"]

    async def test_replace_is_idempotent(self, session: AsyncSession) -> None:
        user = await _make_user(session)
        document = _make_doc(user.id)
        await PostgresDocumentRepository(session).add(document)
        repository = PostgresChunkRepository(session)
        await repository.replace_for_document(
            document.id,
            [Chunk.create(document_id=document.id, content="old", chunk_index=0, token_count=1)],
        )
        await repository.replace_for_document(
            document.id,
            [Chunk.create(document_id=document.id, content="new", chunk_index=0, token_count=1)],
        )
        await session.commit()

        found = await repository.list_for_document(document.id)
        assert [chunk.content for chunk in found] == ["new"]

"""Integration tests for `PostgresUserRepository`.

Mirrors `tests/unit/identity_access/test_in_memory_user_repository.py`
case-for-case — same port, same contract, different adapter — plus a couple
of Postgres-specific cases (persisted round-trip, `update()` on a row that
doesn't exist).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
def repo(session: AsyncSession) -> PostgresUserRepository:
    return PostgresUserRepository(session)


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": "user@example.com",
        "hashed_password": "hashed",
        "full_name": "Test User",
        "role": Role.MEMBER,
    }
    defaults.update(overrides)
    return User.create(**defaults)  # type: ignore[arg-type]


class TestAddAndGetById:
    async def test_get_by_id_returns_none_for_unknown_id(
        self, repo: PostgresUserRepository
    ) -> None:
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_add_then_get_by_id_returns_an_equivalent_user(
        self, repo: PostgresUserRepository, session: AsyncSession
    ) -> None:
        user = _make_user()

        await repo.add(user)
        await session.commit()

        found = await repo.get_by_id(user.id)
        assert found is not None
        assert found.id == user.id
        assert found.email == user.email
        assert found.role is user.role

    async def test_survives_a_new_session(
        self, repo: PostgresUserRepository, session: AsyncSession
    ) -> None:
        """Proves this is real persistence, not an in-memory object identity match."""
        user = _make_user(email="persisted@example.com")
        await repo.add(user)
        await session.commit()

        engine = create_async_engine(TEST_DATABASE_URL)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as other_session:
            other_repo = PostgresUserRepository(other_session)
            found = await other_repo.get_by_email("persisted@example.com")
            assert found is not None
            assert found.id == user.id
        await engine.dispose()


class TestGetByEmail:
    async def test_returns_none_for_unknown_email(self, repo: PostgresUserRepository) -> None:
        assert await repo.get_by_email("nobody@example.com") is None

    async def test_lookup_is_case_insensitive(
        self, repo: PostgresUserRepository, session: AsyncSession
    ) -> None:
        user = _make_user(email="alice@example.com")
        await repo.add(user)
        await session.commit()

        found = await repo.get_by_email("ALICE@EXAMPLE.COM")

        assert found is not None
        assert found.id == user.id


class TestUpdate:
    async def test_update_persists_changes(
        self, repo: PostgresUserRepository, session: AsyncSession
    ) -> None:
        user = _make_user()
        await repo.add(user)
        await session.commit()

        user.rename("Updated Name")
        await repo.update(user)
        await session.commit()

        reloaded = await repo.get_by_id(user.id)
        assert reloaded is not None
        assert reloaded.full_name == "Updated Name"

    async def test_update_of_unknown_user_raises(self, repo: PostgresUserRepository) -> None:
        user = _make_user()  # never added

        with pytest.raises(ValueError, match="no such row"):
            await repo.update(user)


class TestListPage:
    async def test_empty_repo_returns_empty_page(self, repo: PostgresUserRepository) -> None:
        users, has_more = await repo.list_page(limit=10, after_id=None)

        assert users == []
        assert has_more is False

    async def test_respects_limit(
        self, repo: PostgresUserRepository, session: AsyncSession
    ) -> None:
        for i in range(3):
            await repo.add(_make_user(email=f"user{i}@example.com"))
        await session.commit()

        users, has_more = await repo.list_page(limit=2, after_id=None)

        assert len(users) == 2
        assert has_more is True

"""Unit tests for `InMemoryUserRepository`."""

from __future__ import annotations

import uuid

import pytest

from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.in_memory_user_repository import (
    InMemoryUserRepository,
)


@pytest.fixture
def repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


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
        self, repo: InMemoryUserRepository
    ) -> None:
        assert await repo.get_by_id(uuid.uuid4()) is None

    async def test_add_then_get_by_id_returns_the_user(self, repo: InMemoryUserRepository) -> None:
        user = _make_user()

        await repo.add(user)

        assert await repo.get_by_id(user.id) is user


class TestGetByEmail:
    async def test_returns_none_for_unknown_email(self, repo: InMemoryUserRepository) -> None:
        assert await repo.get_by_email("nobody@example.com") is None

    async def test_finds_by_exact_email(self, repo: InMemoryUserRepository) -> None:
        user = _make_user(email="alice@example.com")
        await repo.add(user)

        found = await repo.get_by_email("alice@example.com")

        assert found is not None
        assert found.id == user.id

    async def test_lookup_is_case_insensitive(self, repo: InMemoryUserRepository) -> None:
        user = _make_user(email="alice@example.com")
        await repo.add(user)

        found = await repo.get_by_email("ALICE@EXAMPLE.COM")

        assert found is not None
        assert found.id == user.id


class TestUpdate:
    async def test_update_persists_changes(self, repo: InMemoryUserRepository) -> None:
        user = _make_user()
        await repo.add(user)

        user.rename("Updated Name")
        await repo.update(user)

        reloaded = await repo.get_by_id(user.id)
        assert reloaded is not None
        assert reloaded.full_name == "Updated Name"


class TestListPage:
    async def test_empty_repo_returns_empty_page(self, repo: InMemoryUserRepository) -> None:
        users, has_more = await repo.list_page(limit=10, after_id=None)

        assert users == []
        assert has_more is False

    async def test_respects_limit(self, repo: InMemoryUserRepository) -> None:
        for i in range(3):
            await repo.add(_make_user(email=f"user{i}@example.com"))

        users, has_more = await repo.list_page(limit=2, after_id=None)

        assert len(users) == 2
        assert has_more is True

    async def test_after_id_excludes_items_up_to_and_including_it(
        self, repo: InMemoryUserRepository
    ) -> None:
        added = [_make_user(email=f"user{i}@example.com") for i in range(3)]
        for user in added:
            await repo.add(user)
        ordered = sorted(added, key=lambda u: u.id)

        users, _ = await repo.list_page(limit=10, after_id=ordered[0].id)

        assert ordered[0].id not in {u.id for u in users}
        assert len(users) == 2

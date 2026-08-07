"""Unit tests for `UserService`."""

from __future__ import annotations

import uuid

import pytest

from rag_platform.core.pagination import encode_cursor
from rag_platform.identity_access.application.services.user_service import UserService
from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.exceptions import UserNotFoundError
from rag_platform.identity_access.domain.roles import Role
from rag_platform.identity_access.infrastructure.repositories.in_memory_user_repository import (
    InMemoryUserRepository,
)


@pytest.fixture
def user_repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def user_service(user_repository: InMemoryUserRepository) -> UserService:
    return UserService(user_repository=user_repository)


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": "user@example.com",
        "hashed_password": "hashed",
        "full_name": "Test User",
        "role": Role.MEMBER,
    }
    defaults.update(overrides)
    return User.create(**defaults)  # type: ignore[arg-type]


class TestGetById:
    async def test_returns_the_user(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user()
        await user_repository.add(user)

        found = await user_service.get_by_id(user.id)

        assert found.id == user.id

    async def test_raises_for_unknown_id(self, user_service: UserService) -> None:
        with pytest.raises(UserNotFoundError):
            await user_service.get_by_id(uuid.uuid4())


class TestUpdateProfile:
    async def test_updates_full_name(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user(full_name="Old Name")
        await user_repository.add(user)

        updated = await user_service.update_profile(user.id, full_name="New Name")

        assert updated.full_name == "New Name"

    async def test_persists_the_change(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user(full_name="Old Name")
        await user_repository.add(user)

        await user_service.update_profile(user.id, full_name="New Name")

        reloaded = await user_repository.get_by_id(user.id)
        assert reloaded is not None
        assert reloaded.full_name == "New Name"

    async def test_raises_for_unknown_id(self, user_service: UserService) -> None:
        with pytest.raises(UserNotFoundError):
            await user_service.update_profile(uuid.uuid4(), full_name="New Name")


class TestListUsers:
    async def test_empty_repository_returns_empty_page(self, user_service: UserService) -> None:
        page = await user_service.list_users(limit=10, cursor=None)

        assert page.items == []
        assert page.has_more is False
        assert page.next_cursor is None

    async def test_returns_up_to_limit_items(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        for i in range(5):
            await user_repository.add(_make_user(email=f"user{i}@example.com"))

        page = await user_service.list_users(limit=2, cursor=None)

        assert len(page.items) == 2
        assert page.has_more is True
        assert page.next_cursor is not None

    async def test_cursor_continues_from_where_it_left_off(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        for i in range(5):
            await user_repository.add(_make_user(email=f"user{i}@example.com"))

        first_page = await user_service.list_users(limit=2, cursor=None)
        second_page = await user_service.list_users(limit=2, cursor=first_page.next_cursor)

        first_ids = {u.id for u in first_page.items}
        second_ids = {u.id for u in second_page.items}
        assert first_ids.isdisjoint(second_ids)

    async def test_last_page_has_no_next_cursor(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        for i in range(3):
            await user_repository.add(_make_user(email=f"user{i}@example.com"))

        page = await user_service.list_users(limit=10, cursor=None)

        assert page.has_more is False
        assert page.next_cursor is None

    async def test_invalid_cursor_raises(self, user_service: UserService) -> None:
        from rag_platform.core.pagination import InvalidCursorError

        with pytest.raises(InvalidCursorError):
            await user_service.list_users(limit=10, cursor="not valid!!! 🎉")

    async def test_cursor_for_nonexistent_id_still_works(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        """A cursor encoding a UUID greater than any existing id filters correctly."""
        user = _make_user()
        await user_repository.add(user)
        max_possible_uuid = encode_cursor(str(uuid.UUID(int=2**128 - 1)))

        page = await user_service.list_users(limit=10, cursor=max_possible_uuid)

        assert page.items == []


class TestUpdateRoleAndStatus:
    async def test_updates_role_only(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user(role=Role.MEMBER)
        await user_repository.add(user)

        updated = await user_service.update_role_and_status(user.id, role=Role.ADMIN)

        assert updated.role is Role.ADMIN

    async def test_updates_is_active_only(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user()
        await user_repository.add(user)

        updated = await user_service.update_role_and_status(user.id, is_active=False)

        assert updated.is_active is False

    async def test_can_reactivate_a_deactivated_user(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user()
        user.deactivate()
        await user_repository.add(user)

        updated = await user_service.update_role_and_status(user.id, is_active=True)

        assert updated.is_active is True

    async def test_updates_both(
        self, user_service: UserService, user_repository: InMemoryUserRepository
    ) -> None:
        user = _make_user(role=Role.MEMBER)
        await user_repository.add(user)

        updated = await user_service.update_role_and_status(
            user.id, role=Role.ADMIN, is_active=False
        )

        assert updated.role is Role.ADMIN
        assert updated.is_active is False

    async def test_raises_for_unknown_id(self, user_service: UserService) -> None:
        with pytest.raises(UserNotFoundError):
            await user_service.update_role_and_status(uuid.uuid4(), role=Role.ADMIN)

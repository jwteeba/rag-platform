"""Unit tests for the `User` domain entity."""

from __future__ import annotations

import time

from rag_platform.identity_access.domain.entities import User
from rag_platform.identity_access.domain.roles import Role


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": "user@example.com",
        "hashed_password": "hashed",
        "full_name": "Test User",
        "role": Role.MEMBER,
    }
    defaults.update(overrides)
    return User.create(**defaults)  # type: ignore[arg-type]


class TestUserCreate:
    def test_assigns_a_unique_id(self) -> None:
        first = _make_user()
        second = _make_user()

        assert first.id != second.id

    def test_defaults_to_active(self) -> None:
        user = _make_user()

        assert user.is_active is True

    def test_created_and_updated_timestamps_start_equal(self) -> None:
        user = _make_user()

        assert user.created_at == user.updated_at


class TestUserMutations:
    def test_rename_updates_full_name(self) -> None:
        user = _make_user(full_name="Old Name")

        user.rename("New Name")

        assert user.full_name == "New Name"

    def test_rename_bumps_updated_at(self) -> None:
        user = _make_user()
        original_updated_at = user.updated_at
        time.sleep(0.01)

        user.rename("New Name")

        assert user.updated_at > original_updated_at

    def test_change_role_updates_role(self) -> None:
        user = _make_user(role=Role.MEMBER)

        user.change_role(Role.ADMIN)

        assert user.role is Role.ADMIN

    def test_deactivate_sets_is_active_false(self) -> None:
        user = _make_user()

        user.deactivate()

        assert user.is_active is False

    def test_activate_sets_is_active_true(self) -> None:
        user = _make_user()
        user.deactivate()

        user.activate()

        assert user.is_active is True

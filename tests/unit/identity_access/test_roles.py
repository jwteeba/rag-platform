"""Unit tests for the RBAC role/permission model."""

from __future__ import annotations

from rag_platform.identity_access.domain.roles import Permission, Role, role_has_permission


class TestRolePermissions:
    def test_admin_has_users_read(self) -> None:
        assert role_has_permission(Role.ADMIN, Permission.USERS_READ) is True

    def test_admin_has_users_manage(self) -> None:
        assert role_has_permission(Role.ADMIN, Permission.USERS_MANAGE) is True

    def test_member_lacks_users_read(self) -> None:
        assert role_has_permission(Role.MEMBER, Permission.USERS_READ) is False

    def test_member_lacks_users_manage(self) -> None:
        assert role_has_permission(Role.MEMBER, Permission.USERS_MANAGE) is False

    def test_every_role_has_an_entry_in_the_permission_map(self) -> None:
        from rag_platform.identity_access.domain.roles import ROLE_PERMISSIONS

        for role in Role:
            assert role in ROLE_PERMISSIONS

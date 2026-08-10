"""RBAC model: roles and the permissions each role grants."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """The fixed set of roles a user can hold in Phase 2."""

    ADMIN = "admin"
    MEMBER = "member"


class Permission(StrEnum):
    """Fine-grained permissions checked by the application and API layers.

    Only permissions actually enforced by a Phase 2 endpoint are defined
    here — no speculative permissions for contexts that don't exist yet
    (e.g. no `documents:read`), per the "no placeholder code" rule. Later
    phases add their own permissions to this enum as they add the endpoints
    that check them.
    """

    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({Permission.USERS_READ, Permission.USERS_MANAGE}),
    Role.MEMBER: frozenset(),
}


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Check whether `role` grants `permission`."""
    return permission in ROLE_PERMISSIONS[role]

"""RBAC model: roles and the permissions each role grants.

Scoping decision for Phase 2 (flagged explicitly, same as the ChromaDB and
vector-store flags in earlier phases): this is a **fixed, two-role** model
(`ADMIN`, `MEMBER`), not a fully dynamic role/permission system with
database-backed custom roles. A dynamic system needs persistent storage to
be meaningful (custom roles an admin defines at runtime), and Phase 2 has no
database yet (that's Phase 3). Building dynamic role CRUD against an
in-memory store would be throwaway work, not production-ready infrastructure.

The fixed model is still genuine RBAC — permissions are checked, not roles,
throughout the application and API layers (see `Permission` below and
`identity_access/api/v1/dependencies.py`) — so when Phase 3 or a later phase
wants to make roles dynamic, only `ROLE_PERMISSIONS` and the `Role` type
change; every permission check elsewhere in the codebase is unaffected.
"""

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

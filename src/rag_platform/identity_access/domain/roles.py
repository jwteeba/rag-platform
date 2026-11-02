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
    PROMPT_TEMPLATES_MANAGE = "prompt_templates:manage"
    CACHE_STATS_READ = "cache:stats:read"
    OBSERVABILITY_READ = "observability:read"
    # Document ABAC: members own their documents; admins can manage any.
    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_MANAGE = "documents:manage"
    # Conversation ABAC: members own their conversations; admins can manage any.
    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_MANAGE = "conversations:manage"
    # Search: all authenticated users may search within their own scope.
    SEARCH = "search"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {
            Permission.USERS_READ,
            Permission.USERS_MANAGE,
            Permission.PROMPT_TEMPLATES_MANAGE,
            Permission.CACHE_STATS_READ,
            Permission.OBSERVABILITY_READ,
            Permission.DOCUMENTS_READ,
            Permission.DOCUMENTS_MANAGE,
            Permission.CONVERSATIONS_READ,
            Permission.CONVERSATIONS_MANAGE,
            Permission.SEARCH,
        }
    ),
    Role.MEMBER: frozenset(
        {
            Permission.DOCUMENTS_READ,
            Permission.DOCUMENTS_MANAGE,
            Permission.CONVERSATIONS_READ,
            Permission.CONVERSATIONS_MANAGE,
            Permission.SEARCH,
        }
    ),
}


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Check whether `role` grants `permission`."""
    return permission in ROLE_PERMISSIONS[role]

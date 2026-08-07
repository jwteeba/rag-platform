"""IdentityAccess-specific exceptions.

Each subclasses a generic `core.exceptions` base so the shared error-handling
middleware maps it to the correct HTTP status automatically (see
`status_for_error`'s MRO walk) — no new wiring needed per exception.
"""

from __future__ import annotations

from rag_platform.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
)


class UserNotFoundError(NotFoundError):
    message = "User not found."
    error_type = "user-not-found"


class UserAlreadyExistsError(ConflictError):
    message = "A user with this email already exists."
    error_type = "user-already-exists"


class InvalidCredentialsError(AuthenticationError):
    message = "Incorrect email or password."
    error_type = "invalid-credentials"


class InactiveUserError(AuthenticationError):
    message = "This user account has been deactivated."
    error_type = "inactive-user"


class InvalidTokenError(AuthenticationError):
    message = "The provided token is invalid or has expired."
    error_type = "invalid-token"


class TokenRevokedError(AuthenticationError):
    message = "This token has been revoked."
    error_type = "token-revoked"


class InsufficientPermissionsError(AuthorizationError):
    message = "You do not have the required permission to perform this action."
    error_type = "insufficient-permissions"

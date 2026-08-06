"""Application-wide exception hierarchy.

Every domain and application error raised anywhere in the codebase should
subclass `ApplicationError` rather than a bare `Exception`, so the error
handling middleware (`core/middleware/error_handling.py`) can map it to a
consistent RFC 7807 problem+json response without each route needing its own
try/except block.

Future phases add more specific subclasses as their domains need them (e.g.
`DocumentNotFoundError` in Phase 3, `InvalidCredentialsError` in Phase 2).
Only the base hierarchy needed by Phase 1 (generic + not-found + validation)
is defined here.
"""

from __future__ import annotations


class ApplicationError(Exception):
    """Base class for all application-raised errors.

    Attributes:
        message: Human-readable description of what went wrong.
        error_type: Short machine-readable identifier, used as the RFC 7807
            `type` field suffix (e.g. "not-found", "validation-error").
    """

    message: str = "An unexpected application error occurred."
    error_type: str = "application-error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class NotFoundError(ApplicationError):
    """Raised when a requested resource does not exist."""

    message = "The requested resource was not found."
    error_type = "not-found"


class ValidationError(ApplicationError):
    """Raised when input fails a domain-level validation rule.

    Distinct from FastAPI/Pydantic request-schema validation, which is
    handled separately by FastAPI itself. This is for validation that only
    the application or domain layer can perform (e.g. a rule spanning
    multiple fields or requiring a database lookup).
    """

    message = "The provided input failed validation."
    error_type = "validation-error"


class ConflictError(ApplicationError):
    """Raised when a request conflicts with the current state of a resource."""

    message = "The request conflicts with the current state of the resource."
    error_type = "conflict"

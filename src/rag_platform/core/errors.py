"""RFC 7807 ("Problem Details for HTTP APIs") error representation.

Every error response the API returns — whether raised explicitly by
application code, raised by FastAPI/Pydantic request validation, or an
unhandled exception — is normalized to this shape by the error-handling
middleware. Clients can rely on this structure regardless of which layer
produced the error.
"""

from __future__ import annotations

from http import HTTPStatus

from pydantic import BaseModel, Field

from rag_platform.core.exceptions import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)

_PROBLEM_TYPE_BASE = "https://errors.rag-platform.dev"

_ERROR_STATUS_MAP: dict[type[ApplicationError], HTTPStatus] = {
    NotFoundError: HTTPStatus.NOT_FOUND,
    ValidationError: HTTPStatus.UNPROCESSABLE_ENTITY,
    ConflictError: HTTPStatus.CONFLICT,
    AuthenticationError: HTTPStatus.UNAUTHORIZED,
    AuthorizationError: HTTPStatus.FORBIDDEN,
}


class ProblemDetail(BaseModel):
    """RFC 7807 problem details payload.

    Field names intentionally match the RFC exactly (`type`, `title`,
    `status`, `detail`, `instance`) so the response is spec-compliant for any
    client that understands `application/problem+json`.
    """

    type: str = Field(description="A URI identifying the error type.")
    title: str = Field(description="A short, human-readable summary of the error type.")
    status: int = Field(description="The HTTP status code for this occurrence of the error.")
    detail: str = Field(description="A human-readable explanation specific to this occurrence.")
    instance: str = Field(description="A URI identifying this specific occurrence of the error.")
    request_id: str | None = Field(
        default=None, description="Correlates this error with server-side logs and traces."
    )


def status_for_error(error: ApplicationError) -> HTTPStatus:
    """Resolve the HTTP status code for a given application error type.

    Walks the exception's MRO so subclasses of a mapped error type (e.g. a
    future `DocumentNotFoundError(NotFoundError)`) resolve correctly without
    needing their own map entry.
    """
    for error_type in type(error).__mro__:
        if error_type in _ERROR_STATUS_MAP:
            return _ERROR_STATUS_MAP[error_type]
    return HTTPStatus.INTERNAL_SERVER_ERROR


def build_problem_detail(
    *,
    error_type: str,
    status: HTTPStatus,
    detail: str,
    instance: str,
    request_id: str | None = None,
) -> ProblemDetail:
    """Construct a `ProblemDetail` with a consistent `type` URI scheme."""
    return ProblemDetail(
        type=f"{_PROBLEM_TYPE_BASE}/{error_type}",
        title=status.phrase,
        status=int(status),
        detail=detail,
        instance=instance,
        request_id=request_id,
    )

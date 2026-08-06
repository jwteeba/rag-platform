"""Global error-handling middleware.

This is the *only* place in the codebase that converts an exception into an
HTTP response. Routes and services raise `ApplicationError` subclasses (or
let unexpected exceptions propagate) and never construct error JSON
themselves — that keeps the API layer thin, per the architecture rules.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from rag_platform.core.errors import build_problem_detail, status_for_error
from rag_platform.core.exceptions import ApplicationError
from rag_platform.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

logger = get_logger(__name__)

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catch exceptions and translate them into RFC 7807 responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except ApplicationError as exc:
            status = status_for_error(exc)
            logger.warning(
                "application_error",
                error_type=exc.error_type,
                detail=exc.message,
                path=request.url.path,
            )
            problem = build_problem_detail(
                error_type=exc.error_type,
                status=status,
                detail=exc.message,
                instance=str(request.url.path),
                request_id=getattr(request.state, "request_id", None),
            )
            return JSONResponse(
                status_code=int(status),
                content=problem.model_dump(),
                media_type=PROBLEM_JSON_MEDIA_TYPE,
            )
        except Exception:
            logger.exception("unhandled_exception", path=request.url.path)
            problem = build_problem_detail(
                error_type="internal-server-error",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while processing the request.",
                instance=str(request.url.path),
                request_id=getattr(request.state, "request_id", None),
            )
            return JSONResponse(
                status_code=500,
                content=problem.model_dump(),
                media_type=PROBLEM_JSON_MEDIA_TYPE,
            )

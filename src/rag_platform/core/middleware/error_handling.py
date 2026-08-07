"""Global error handling: middleware plus explicit exception handlers.

Three layers work together to guarantee every error response is RFC 7807:

1. `ErrorHandlingMiddleware` catches `ApplicationError` subclasses raised by
   our own routes/services, and any truly unhandled exception (→ 500).
2. `http_exception_handler` catches `HTTPException` — raised either by our
   own code or, importantly, by FastAPI/Starlette internals (e.g.
   `OAuth2PasswordBearer` raises a plain `HTTPException` when no bearer
   token is present). Starlette's built-in exception middleware intercepts
   `HTTPException` *before* it would ever reach our `BaseHTTPMiddleware`, so
   without this explicit handler those responses fall back to FastAPI's
   default `{"detail": ...}` shape instead of RFC 7807. This is why it's a
   separate handler rather than another `except` clause in the middleware.
3. `validation_error_handler` catches `RequestValidationError` — Pydantic
   request-body/query/path validation failures — for the same reason, and
   attaches the per-field errors as an RFC 7807 extension member.

Routes and services never construct error JSON themselves — that's what
keeps the API layer thin, per the architecture rules.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, cast

from fastapi.encoders import jsonable_encoder
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from rag_platform.core.errors import build_problem_detail, status_for_error
from rag_platform.core.exceptions import ApplicationError, AuthenticationError
from rag_platform.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException
    from starlette.requests import Request
    from starlette.responses import Response

logger = get_logger(__name__)

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"


def _request_id(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else None


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Catch `ApplicationError`s and unhandled exceptions; translate to RFC 7807.

    Does *not* need to handle `HTTPException` or `RequestValidationError` —
    see `http_exception_handler` / `validation_error_handler` below for why
    those are registered separately via `app.add_exception_handler`.
    """

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
                request_id=_request_id(request),
            )
            return JSONResponse(
                status_code=int(status),
                content=problem.model_dump(),
                media_type=PROBLEM_JSON_MEDIA_TYPE,
                headers=(
                    {"WWW-Authenticate": "Bearer"} if isinstance(exc, AuthenticationError) else None
                ),
            )
        except Exception:
            logger.exception("unhandled_exception", path=request.url.path)
            problem = build_problem_detail(
                error_type="internal-server-error",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred while processing the request.",
                instance=str(request.url.path),
                request_id=_request_id(request),
            )
            return JSONResponse(
                status_code=500,
                content=problem.model_dump(),
                media_type=PROBLEM_JSON_MEDIA_TYPE,
            )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """RFC 7807 handler for FastAPI/Starlette's built-in `HTTPException`.

    Covers cases our own code never raises directly, e.g.
    `OAuth2PasswordBearer` raising 401 when no bearer token is supplied, or
    a 404 for a path that matches no route.

    `exc` is typed as `Exception` rather than `HTTPException` to match
    Starlette's `ExceptionHandler` signature exactly (it's invariant on the
    handler's exception parameter type); FastAPI only ever calls this
    handler with an `HTTPException`, per the registration in `main.py`.
    """
    exc = cast("HTTPException", exc)
    status = HTTPStatus(exc.status_code)
    error_type = status.phrase.lower().replace(" ", "-")
    logger.warning("http_exception", status_code=exc.status_code, path=request.url.path)
    problem = build_problem_detail(
        error_type=error_type,
        status=status,
        detail=str(exc.detail),
        instance=str(request.url.path),
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=exc.headers,
    )


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """RFC 7807 handler for FastAPI's request validation errors (422).

    Adds the per-field error list as `errors`, an RFC 7807 extension member
    (the spec explicitly permits additional members beyond the standard
    five) — losing that detail would make client-side form validation
    guesswork.
    """
    exc = cast("RequestValidationError", exc)
    logger.warning("validation_error", path=request.url.path, errors=exc.errors())
    problem = build_problem_detail(
        error_type="validation-error",
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail="The request failed validation.",
        instance=str(request.url.path),
        request_id=_request_id(request),
    )
    content = problem.model_dump()
    content["errors"] = jsonable_encoder(exc.errors())
    return JSONResponse(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        content=content,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
    )

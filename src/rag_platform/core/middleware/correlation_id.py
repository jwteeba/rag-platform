"""Correlation ID middleware.

Distinct from the request ID: a request ID identifies one hop through this
service; a correlation ID identifies a logical operation that may span
multiple services and multiple requests (e.g. a chat turn that fans out to
retrieval, embedding, and generation calls). If the caller supplies one, it
is propagated as-is; otherwise a new one is minted, meaning this service is
the origin of the operation.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Propagate or originate a correlation ID for cross-service tracing."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming_id = request.headers.get(CORRELATION_ID_HEADER)
        correlation_id = incoming_id if incoming_id else str(uuid.uuid4())

        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response

"""FastAPI application factory.

`create_app()` is the single place the application is assembled: settings
loaded, logging configured, the DI container built, middleware registered
(in the order that matters — see the comment above `add_middleware` calls
below), and routers mounted. `main.py` itself contains no business logic
and no route handlers.

Uvicorn entry point: `rag_platform.main:app`.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from rag_platform.core.config import Settings, get_settings
from rag_platform.core.logging import configure_logging, get_logger
from rag_platform.core.middleware.correlation_id import CorrelationIDMiddleware
from rag_platform.core.middleware.error_handling import (
    ErrorHandlingMiddleware,
    http_exception_handler,
    validation_error_handler,
)
from rag_platform.core.middleware.request_id import RequestIDMiddleware
from rag_platform.di.containers import build_container, ensure_bootstrap_admin
from rag_platform.identity_access.api.v1.auth_router import router as auth_router
from rag_platform.identity_access.api.v1.users_router import router as users_router
from rag_platform.platform.health.router import router as health_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

logger = get_logger(__name__)


def _build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = build_container(settings)
        await ensure_bootstrap_admin(app.state.container, settings)
        logger.info("application_startup_complete")
        yield

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application instance.

    Args:
        settings: Optional pre-built settings, primarily for tests that need
            a non-default configuration. Defaults to `get_settings()`.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.name,
        version=settings.version,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=_build_lifespan(settings),
    )

    # Middleware order matters: Starlette applies them as nested layers, so
    # the LAST one added is the OUTERMOST — it sees the request first and
    # the response last. We want, from outermost to innermost:
    #   1. Error handling  — must wrap everything so no exception below it
    #      escapes as an unformatted 500.
    #   2. Request ID       — every log line, including error logs, should
    #      carry it.
    #   3. Correlation ID   — same reasoning as request ID.
    #   4. Trusted host / CORS — standard perimeter concerns.
    # Registered here in reverse (innermost-first) order accordingly.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)

    # `HTTPException`/`RequestValidationError` are intercepted by Starlette's
    # own exception middleware *before* they'd reach `ErrorHandlingMiddleware`
    # above — these explicit handlers are what keep those responses RFC 7807
    # too. See the module docstring in `core/middleware/error_handling.py`.
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(users_router, prefix=settings.api_v1_prefix)

    logger.info(
        "application_configured",
        environment=settings.environment.value,
        version=settings.version,
    )

    return app


app = create_app()

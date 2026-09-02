"""Liveness and readiness endpoints.

Kept deliberately outside `/api/v1` — health checks are an infrastructure
concern consumed by whatever container orchestrator or PaaS ends up running
this service (Kubernetes, ECS, Render, Nomad, etc. — the deployment target
is intentionally left platform-agnostic, see ADR-0004), not a versioned
business API, so they aren't subject to API versioning or client-facing
deprecation policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from rag_platform.core.config import Settings, get_settings
from rag_platform.core.logging import get_logger
from rag_platform.platform.health.schemas import LivenessResponse, ReadinessResponse

if TYPE_CHECKING:
    from rag_platform.di.containers import Container

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Returns 200 if the process is running. Never checks downstream dependencies.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Returns 200 if every downstream dependency check passes, 503 otherwise "
        "(so an orchestrator's readiness probe correctly stops routing traffic here)."
    ),
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    settings: Settings = get_settings()
    container: Container = request.app.state.container

    checks: dict[str, str] = {
        "database": await _check_database(container),
        "redis": await _check_redis(container),
        "storage": await _check_storage(container, settings),
    }

    all_ok = all(result == "ok" for result in checks.values())
    if not all_ok:
        response.status_code = 503
        logger.warning("readiness_check_failed", checks=checks)

    return ReadinessResponse(
        status="ok" if all_ok else "degraded",
        version=settings.version,
        checks=checks,
    )


async def _check_database(container: Container) -> str:
    """Run a trivial query to confirm the database is reachable.

    Returns "ok", or a short error description — never raises, since a
    readiness probe failing to check a dependency should report that
    dependency as down, not 500 the whole endpoint.
    """
    try:
        async with container.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # deliberately broad — see docstring
        return f"unreachable: {exc}"
    return "ok"


async def _check_redis(container: Container) -> str:
    """Ping Redis to confirm it's reachable. Same never-raises contract as
    `_check_database` above."""
    try:
        await container.redis_client.ping()
    except Exception as exc:  # deliberately broad — see docstring
        return f"unreachable: {exc}"
    return "ok"


async def _check_storage(container: Container, settings: Settings) -> str:
    """Check MinIO bucket reachability. Same never-raises contract."""
    import asyncio

    try:
        await asyncio.to_thread(container.minio_client.bucket_exists, settings.minio_bucket)
    except Exception as exc:  # deliberately broad — see docstring
        return f"unreachable: {exc}"
    return "ok"

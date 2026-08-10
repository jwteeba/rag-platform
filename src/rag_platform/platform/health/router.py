"""Liveness and readiness endpoints."""

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

    checks: dict[str, str] = {"database": await _check_database(container)}

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

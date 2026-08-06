"""Liveness and readiness endpoints.

Kept deliberately outside `/api/v1` — health checks are an infrastructure
concern consumed by whatever container orchestrator or PaaS ends up running
this service (Kubernetes, ECS, Render, Nomad, etc. — the deployment target
is intentionally left platform-agnostic, see ADR-0004), not a versioned
business API, so they aren't subject to API versioning or client-facing
deprecation policy.
"""

from __future__ import annotations

from fastapi import APIRouter

from rag_platform.core.config import Settings, get_settings
from rag_platform.platform.health.schemas import LivenessResponse, ReadinessResponse

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
    description="Returns 200 if the process is ready to accept traffic.",
)
async def readiness() -> ReadinessResponse:
    settings: Settings = get_settings()
    return ReadinessResponse(version=settings.version)

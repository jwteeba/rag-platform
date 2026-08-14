"""Response schemas for the health endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Indicates the process is running and able to serve requests at all.

    Liveness must never depend on downstream systems (database, cache,
    vector store, etc.) — a downstream outage should surface as a readiness
    failure, not cause the orchestrator to kill and restart otherwise-healthy
    pods.
    """

    status: str = Field(default="ok", description="Always 'ok' if this response is returned.")


class ReadinessResponse(BaseModel):
    """Indicates the process is ready to accept traffic.

    As of Phase 3, readiness includes an actual database connectivity
    check (see `router.py`) — the process can be alive without being ready
    if Postgres is unreachable. Redis and other dependencies get their own
    check as they're introduced (Phase 4, etc.).
    """

    status: str = Field(description="'ok' if every check passed, 'degraded' otherwise.")
    version: str = Field(description="Deployed application version.")
    checks: dict[str, str] = Field(
        description="Per-dependency status ('ok' or an error message), keyed by dependency name."
    )

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

    As dependencies are introduced in later phases (database in Phase 3,
    Redis in Phase 4, etc.), this endpoint will check each of them and
    report per-dependency status. In Phase 1 there are no external
    dependencies yet, so readiness is equivalent to liveness.
    """

    status: str = Field(default="ok", description="'ok' if the service is ready to accept traffic.")
    version: str = Field(description="Deployed application version.")

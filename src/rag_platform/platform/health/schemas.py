"""Response schemas for the health endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Indicates the process is running and able to serve requests at all."""

    status: str = Field(default="ok", description="Always 'ok' if this response is returned.")


class ReadinessResponse(BaseModel):
    """Indicates the process is ready to accept traffic."""

    status: str = Field(description="'ok' if every check passed, 'degraded' otherwise.")
    version: str = Field(description="Deployed application version.")
    checks: dict[str, str] = Field(
        description="Per-dependency status ('ok' or an error message), keyed by dependency name."
    )

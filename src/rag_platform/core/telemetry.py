"""OpenTelemetry setup and small helpers for non-instrumented clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from rag_platform.core.config import Settings

_configured = False
_sqlalchemy_instrumented_engines: set[int] = set()


def configure_tracing(settings: Settings) -> None:
    """Configure process-wide tracing once, using a swappable OTLP exporter.

    No-op when `otel_enabled` is False. Connection failures to the collector
    are non-fatal — the BatchSpanProcessor will retry in the background and
    drop spans if the collector remains unreachable.
    """
    global _configured
    if _configured or not settings.otel_enabled:
        return
    try:
        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_endpoint))
        )
        trace.set_tracer_provider(provider)
        RedisInstrumentor().instrument()
        _configured = True
    except Exception:
        # Never crash startup over a missing collector.
        from rag_platform.core.logging import get_logger

        get_logger(__name__).warning(
            "otel_setup_failed",
            endpoint=settings.otel_endpoint,
            hint="Traces will not be exported. Start the OTEL collector or "
            "set APP_OTEL_ENABLED=false.",
        )


def instrument_sqlalchemy(engine: AsyncEngine, settings: Settings) -> None:
    """Instrument each runtime engine once (engines are created in lifespan/tasks)."""
    identity = id(engine)
    if settings.otel_enabled and identity not in _sqlalchemy_instrumented_engines:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        _sqlalchemy_instrumented_engines.add(identity)


def get_tracer(name: str):  # type: ignore[no-untyped-def]
    """Return an OTel tracer; it is a no-op when telemetry is disabled."""
    return trace.get_tracer(name)

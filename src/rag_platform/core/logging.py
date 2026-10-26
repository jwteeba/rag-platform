"""Structured logging configuration.

Uses `structlog` for every log line in the application. Request ID and
correlation ID are bound into a `structlog` contextvars context by the
middleware in `core/middleware/`, so every log emitted while handling a
request automatically carries both identifiers without any call site having
to pass them explicitly.

`configure_logging()` must be called exactly once, during application
startup (see `main.py`), before any logger is used.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog
from opentelemetry import trace

from rag_platform.core.config import LogFormat, Settings

if TYPE_CHECKING:
    from collections.abc import MutableMapping


def add_trace_context(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Attach the active OpenTelemetry identifiers to every structured event."""
    context = trace.get_current_span().get_span_context()
    event_dict["trace_id"] = format(context.trace_id, "032x") if context.is_valid else None
    event_dict["span_id"] = format(context.span_id, "016x") if context.is_valid else None
    # Stable alert dimensions make platform-specific log rules portable.
    event_dict.setdefault("error_type", None)
    event_dict.setdefault("document_id", None)
    event_dict.setdefault("user_id", None)
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure `structlog` and the standard library logging it wraps.

    Args:
        settings: Application settings, used to decide the renderer
            (console vs. JSON) and the minimum log level.
    """
    log_level = getattr(logging, settings.log_level.value)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_trace_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format is LogFormat.JSON:
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Uvicorn's own loggers should flow through the same structured pipeline
    # instead of double-logging in their default format.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a `structlog` bound logger for the given module/component name."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger

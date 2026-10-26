"""Celery task base that carries structlog context across process boundaries."""

from __future__ import annotations

import time
from typing import Any

import structlog
from celery import Task
from opentelemetry import context, propagate

from rag_platform.core.logging import get_logger
from rag_platform.core.telemetry import get_tracer

logger = get_logger(__name__)
_CONTEXT_HEADER = "structlog_context"


class StructuredLoggingTask(Task):  # type: ignore[misc]
    """Propagate serializable structlog context in Celery message headers."""

    abstract = True

    def apply_async(self, args: Any = None, kwargs: Any = None, **options: Any) -> Any:
        headers = dict(options.pop("headers", {}) or {})
        # Request/correlation IDs are strings today. Filtering also ensures a
        # future non-JSON context value can never break task publication.
        headers[_CONTEXT_HEADER] = {
            key: value
            for key, value in structlog.contextvars.get_contextvars().items()
            if isinstance(value, str | int | float | bool | type(None))
        }
        propagate.inject(headers)
        return super().apply_async(args=args, kwargs=kwargs, headers=headers, **options)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        structlog.contextvars.clear_contextvars()
        request_headers = getattr(self.request, "headers", None) or {}
        structlog_context = request_headers.get(_CONTEXT_HEADER, {})
        if isinstance(structlog_context, dict):
            structlog.contextvars.bind_contextvars(**structlog_context)
        logger.info("background_task_started", task_name=self.name, task_id=self.request.id)
        started_at = time.perf_counter()
        self.request._observability_started_at = started_at
        token = propagate.extract(request_headers)
        context_token = context.attach(token)
        try:
            with get_tracer(__name__).start_as_current_span(f"celery.{self.name}") as span:
                span.set_attribute("celery.task_id", str(self.request.id))
                return self.run(*args, **kwargs)
        except Exception:
            logger.exception(
                "background_task_failed",
                task_name=self.name,
                task_id=self.request.id,
                outcome="failure",
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
            )
            raise
        finally:
            context.detach(context_token)

    def after_return(
        self, status: str, retval: Any, task_id: str, args: Any, kwargs: Any, einfo: Any
    ) -> None:
        started_at = getattr(self.request, "_observability_started_at", None)
        duration_ms = (
            round((time.perf_counter() - started_at) * 1000, 3)
            if isinstance(started_at, float)
            else None
        )
        outcome = {"SUCCESS": "success", "RETRY": "retry"}.get(status, "failure")
        logger.info(
            "background_task_finished",
            task_name=self.name,
            task_id=task_id,
            status=status,
            outcome=outcome,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()
        super().after_return(status, retval, task_id, args, kwargs, einfo)

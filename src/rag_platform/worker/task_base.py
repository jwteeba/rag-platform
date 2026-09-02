"""Celery task base that carries structlog context across process boundaries."""

from __future__ import annotations

from typing import Any

import structlog
from celery import Task

from rag_platform.core.logging import get_logger

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
        return super().apply_async(args=args, kwargs=kwargs, headers=headers, **options)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        structlog.contextvars.clear_contextvars()
        request_headers = getattr(self.request, "headers", None) or {}
        context = request_headers.get(_CONTEXT_HEADER, {})
        if isinstance(context, dict):
            structlog.contextvars.bind_contextvars(**context)
        logger.info("background_task_started", task_name=self.name, task_id=self.request.id)
        return self.run(*args, **kwargs)

    def after_return(
        self, status: str, retval: Any, task_id: str, args: Any, kwargs: Any, einfo: Any
    ) -> None:
        logger.info("background_task_finished", task_name=self.name, task_id=task_id, status=status)
        structlog.contextvars.clear_contextvars()
        super().after_return(status, retval, task_id, args, kwargs, einfo)

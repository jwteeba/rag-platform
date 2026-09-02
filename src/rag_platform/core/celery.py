"""Celery application factory shared by API producers and worker processes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from celery import Celery

from rag_platform.core.config import get_settings

if TYPE_CHECKING:
    from rag_platform.core.config import Settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Create a configured Celery app and discover bounded-context tasks."""
    settings = settings or get_settings()
    # Importing the concrete base here avoids a process-global Celery config
    # while retaining the context propagation behaviour for every task.
    from rag_platform.worker.task_base import StructuredLoggingTask

    app = Celery("rag_platform", task_cls=StructuredLoggingTask)
    app.conf.update(
        broker_url=settings.resolved_celery_broker_url,
        result_backend=settings.resolved_celery_result_backend,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_time_limit=settings.celery_task_time_limit_seconds,
        task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
        task_always_eager=settings.celery_task_always_eager,
        task_eager_propagates=settings.celery_task_eager_propagates,
    )
    app.autodiscover_tasks(["rag_platform.document_management"])
    return app


# Importing this module expose the Celery application for both
# ``.delay()`` producers and ``celery -A rag_platform.worker worker``.
celery_app = create_celery_app()

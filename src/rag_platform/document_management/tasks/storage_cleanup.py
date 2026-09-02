"""Retryable cleanup of objects orphaned by a completed document deletion."""

from __future__ import annotations

from rag_platform.core.celery import celery_app
from rag_platform.core.config import get_settings
from rag_platform.core.logging import get_logger
from rag_platform.core.storage import build_minio_client

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="document_management.storage_cleanup",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def cleanup_storage_object(task: object, storage_key: str) -> str:
    """Delete an orphaned object; repeated deletes are safe with MinIO/S3."""
    settings = get_settings()
    client = build_minio_client(settings)
    client.remove_object(settings.minio_bucket, storage_key)
    task_id = getattr(getattr(task, "request", None), "id", None)
    logger.info("orphaned_storage_object_cleaned", storage_key=storage_key, task_id=task_id)
    return storage_key


def enqueue_storage_cleanup(storage_key: str) -> None:
    """Publish cleanup without letting broker availability affect the API."""
    cleanup_storage_object.delay(storage_key)

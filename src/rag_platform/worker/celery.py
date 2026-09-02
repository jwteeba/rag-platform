"""Celery CLI entry point: ``celery -A rag_platform.worker.celery worker``."""

from rag_platform.core.celery import celery_app

__all__ = ["celery_app"]

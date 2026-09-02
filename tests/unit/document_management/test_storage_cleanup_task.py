"""Eager-mode tests for the orphaned-object Celery task."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from celery.exceptions import Retry

from rag_platform.core.celery import celery_app
from rag_platform.document_management.tasks.storage_cleanup import cleanup_storage_object


@pytest.fixture(autouse=True)
def eager_celery() -> None:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


def test_cleanup_task_deletes_the_orphaned_object(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr(
        "rag_platform.document_management.tasks.storage_cleanup.build_minio_client",
        lambda _: client,
    )

    result = cleanup_storage_object.delay("documents/orphan.pdf")

    assert result.get() == "documents/orphan.pdf"
    client.remove_object.assert_called_once_with("rag-platform", "documents/orphan.pdf")


def test_cleanup_task_retries_transient_storage_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.remove_object.side_effect = RuntimeError("temporary failure")
    monkeypatch.setattr(
        "rag_platform.document_management.tasks.storage_cleanup.build_minio_client",
        lambda _: client,
    )

    with pytest.raises(Retry, match="temporary failure"):
        cleanup_storage_object.delay("documents/orphan.pdf")

    assert client.remove_object.call_count == 1

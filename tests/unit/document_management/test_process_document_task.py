from __future__ import annotations

import asyncio
import uuid

import pytest

from rag_platform.core.celery import celery_app
from rag_platform.document_management.tasks.process_document import process_document


@pytest.fixture(autouse=True)
def eager_celery() -> None:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


def test_process_task_runs_pipeline_in_eager_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid.uuid4()
    monkeypatch.setattr(
        "rag_platform.document_management.tasks.process_document._process",
        lambda _: asyncio.sleep(0, result=2),
    )

    assert process_document.delay(str(document_id)).get() == 2

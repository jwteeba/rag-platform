"""Unit tests for the embed_chunks Celery task."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest

from rag_platform.core.celery import celery_app
from rag_platform.indexing.tasks.embed_chunks import embed_chunks


@pytest.fixture(autouse=True)
def eager_celery() -> None:
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


def test_embed_task_runs_in_eager_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid.uuid4()
    monkeypatch.setattr(
        "rag_platform.indexing.tasks.embed_chunks._embed",
        lambda _: asyncio.sleep(0, result=3),
    )

    assert embed_chunks.delay(str(document_id)).get() == 3


def test_embed_task_marks_failed_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    document_id = uuid.uuid4()
    marked_failed: list[uuid.UUID] = []

    async def fake_mark_failed(doc_id: uuid.UUID) -> None:
        marked_failed.append(doc_id)

    async def always_fail(_: uuid.UUID) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr("rag_platform.indexing.tasks.embed_chunks._embed", always_fail)
    monkeypatch.setattr(
        "rag_platform.indexing.tasks.embed_chunks._mark_chunks_failed", fake_mark_failed
    )

    with patch.object(embed_chunks, "max_retries", 0), pytest.raises(RuntimeError, match="boom"):
        embed_chunks.delay(str(document_id)).get()

    assert marked_failed == [document_id]

from __future__ import annotations

import uuid

import pytest

from rag_platform.document_management.application.services.chunking_service import ChunkingService


def test_sliding_window_preserves_configured_overlap() -> None:
    chunks = ChunkingService(chunk_size_tokens=3, chunk_overlap_tokens=1, max_chunks=10).chunk(
        document_id=uuid.uuid4(), text="one two three four five"
    )

    assert [chunk.content for chunk in chunks] == ["one two three", "three four five"]
    assert [chunk.token_count for chunk in chunks] == [3, 3]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]


def test_empty_text_produces_no_chunks() -> None:
    service = ChunkingService(chunk_size_tokens=3, chunk_overlap_tokens=1, max_chunks=10)
    assert service.chunk(document_id=uuid.uuid4(), text="   ") == []


def test_chunk_limit_is_enforced() -> None:
    service = ChunkingService(chunk_size_tokens=2, chunk_overlap_tokens=0, max_chunks=1)
    with pytest.raises(ValueError, match="max_chunks"):
        service.chunk(document_id=uuid.uuid4(), text="one two three")

"""Deterministic sliding-window chunking for extracted text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_platform.document_management.domain.entities import Chunk

if TYPE_CHECKING:
    import uuid


class ChunkingService:
    """Split whitespace tokens with overlap, preserving readable text."""

    def __init__(
        self, *, chunk_size_tokens: int, chunk_overlap_tokens: int, max_chunks: int
    ) -> None:
        if chunk_overlap_tokens >= chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens must be smaller than chunk_size_tokens")
        self._size = chunk_size_tokens
        self._overlap = chunk_overlap_tokens
        self._max_chunks = max_chunks

    def chunk(self, *, document_id: uuid.UUID, text: str) -> list[Chunk]:
        tokens = text.split()
        if not tokens:
            return []
        chunks: list[Chunk] = []
        step = self._size - self._overlap
        for start in range(0, len(tokens), step):
            window = tokens[start : start + self._size]
            if not window:
                break
            if len(chunks) >= self._max_chunks:
                raise ValueError("document exceeds max_chunks_per_document")
            chunks.append(
                Chunk.create(
                    document_id=document_id,
                    content=" ".join(window),
                    chunk_index=len(chunks),
                    token_count=len(window),
                )
            )
            if start + self._size >= len(tokens):
                break
        return chunks

"""Indexing domain ports.

Framework-free interfaces only. Infrastructure adapters live in
`indexing/infrastructure/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingPort(Protocol):
    """Produce dense vector embeddings for a list of text strings.

    Implementations must be safe to call from a Celery task (i.e. they may
    be synchronous — the task runner wraps them in `asyncio.to_thread` if
    needed, or calls them directly in a sync context).
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...

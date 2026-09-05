"""OpenAI embedding adapter.

Calls the OpenAI Embeddings API in batches. Uses the synchronous `openai`
client — appropriate for Celery tasks, which run in a thread pool, not an
async event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openai import OpenAI

if TYPE_CHECKING:
    from rag_platform.core.config import Settings


class OpenAIEmbeddingAdapter:
    """Implements `EmbeddingPort` using the OpenAI Embeddings API."""

    def __init__(self, settings: Settings) -> None:
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self._batch_size = settings.embedding_batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = self._client.embeddings.create(input=batch, model=self._model)
            results.extend(item.embedding for item in response.data)
        return results

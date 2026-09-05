"""Local sentence-transformers embedding adapter.

Uses a locally-loaded model (no external API call). Suitable for development
and air-gapped deployments. Swap in by setting APP_EMBEDDING_PROVIDER=local.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from rag_platform.core.config import Settings


class SentenceTransformerEmbeddingAdapter:
    """Implements `EmbeddingPort` using a local sentence-transformers model."""

    def __init__(self, settings: Settings) -> None:
        self._model = SentenceTransformer(settings.embedding_model)
        self._batch_size = settings.embedding_batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

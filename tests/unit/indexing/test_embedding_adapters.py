"""Unit tests for embedding adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag_platform.core.config import Settings


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "embedding_batch_size": 2,
        "openai_api_key": "sk-test",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


class TestOpenAIEmbeddingAdapter:
    def test_embed_returns_vectors_in_order(self) -> None:
        from rag_platform.indexing.infrastructure.embedding.openai_adapter import (
            OpenAIEmbeddingAdapter,
        )

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[
                MagicMock(embedding=[0.1, 0.2]),
                MagicMock(embedding=[0.3, 0.4]),
            ]
        )

        with patch(
            "rag_platform.indexing.infrastructure.embedding.openai_adapter.OpenAI",
            return_value=mock_client,
        ):
            adapter = OpenAIEmbeddingAdapter(_settings())
            result = adapter.embed(["hello", "world"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_batches_requests(self) -> None:
        from rag_platform.indexing.infrastructure.embedding.openai_adapter import (
            OpenAIEmbeddingAdapter,
        )

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[float(i)]) for i in range(2)]
        )

        with patch(
            "rag_platform.indexing.infrastructure.embedding.openai_adapter.OpenAI",
            return_value=mock_client,
        ):
            adapter = OpenAIEmbeddingAdapter(_settings(embedding_batch_size=2))
            adapter.embed(["a", "b", "c", "d"])

        # 4 texts with batch_size=2 → 2 API calls
        assert mock_client.embeddings.create.call_count == 2

    def test_embed_empty_list_returns_empty(self) -> None:
        from rag_platform.indexing.infrastructure.embedding.openai_adapter import (
            OpenAIEmbeddingAdapter,
        )

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = MagicMock(data=[])

        with patch(
            "rag_platform.indexing.infrastructure.embedding.openai_adapter.OpenAI",
            return_value=mock_client,
        ):
            adapter = OpenAIEmbeddingAdapter(_settings())
            assert adapter.embed([]) == []


class TestSentenceTransformerEmbeddingAdapter:
    def test_embed_returns_vectors(self) -> None:
        import numpy as np

        pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

        from rag_platform.indexing.infrastructure.embedding.sentence_transformer_adapter import (
            SentenceTransformerEmbeddingAdapter,
        )

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])

        with patch(
            "rag_platform.indexing.infrastructure.embedding.sentence_transformer_adapter.SentenceTransformer",
            return_value=mock_model,
        ):
            adapter = SentenceTransformerEmbeddingAdapter(
                _settings(embedding_provider="local", embedding_model="all-MiniLM-L6-v2")
            )
            result = adapter.embed(["hello", "world"])

        assert result == pytest.approx([[0.1, 0.2], [0.3, 0.4]])

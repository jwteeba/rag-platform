"""Qdrant client construction and collection bootstrap helper.

Mirrors `core/storage.py`'s role for MinIO — framework-light, no FastAPI.
The qdrant-client is synchronous by default; callers that need async
behaviour should wrap in `asyncio.to_thread`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from rag_platform.core.config import Environment

if TYPE_CHECKING:
    from rag_platform.core.config import Settings


def build_qdrant_client(settings: Settings) -> QdrantClient:
    """Create a Qdrant client from application settings.

    Supports:
    - Local Qdrant without authentication.
    - Qdrant Cloud with API-key authentication.
    """

    if settings.environment == Environment.TESTING:
        return QdrantClient(":memory:")

    return QdrantClient(
        url=settings.qdrant_host,
        api_key=settings.qdrant_api_key or None,
        https=settings.qdrant_https,  # explicit, not inferred from api_key
    )


def ensure_collection_exists(client: QdrantClient, settings: Settings) -> None:
    """Create the Qdrant collection if it does not already exist.

    Idempotent — safe to call on every startup. Runs synchronously; callers
    that need async behaviour should wrap in `asyncio.to_thread`.

    Payload fields (`document_id`, `chunk_id`, `owner_id`, `chunk_index`)
    are stored as Qdrant point payload — no schema declaration needed, Qdrant
    accepts arbitrary JSON payload. The vector dimension must match the
    configured embedding model.
    """
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection_name not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )

    # Ensure payload indexes exist for fields used in every search filter.
    # `create_payload_index` is idempotent — safe to call on every startup
    # whether the collection was just created or already existed.
    collection_name = settings.qdrant_collection_name
    client.create_payload_index(
        collection_name=collection_name,
        field_name="owner_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=collection_name,
        field_name="document_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )

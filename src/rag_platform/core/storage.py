"""MinIO client construction and bucket bootstrap helper.

Framework-light (the `minio` library only, no FastAPI) by design, per the
Shared/Core layering rule — mirrors `core/db.py`'s role for Postgres and
`core/cache.py`'s role for Redis.

The MinIO SDK is synchronous; every call site in this codebase wraps it in
`asyncio.to_thread` (see `document_management/infrastructure/storage/`) so
the event loop is never blocked.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from minio import Minio

if TYPE_CHECKING:
    from rag_platform.core.config import Settings


def build_minio_client(settings: Settings) -> Minio:
    """Create a MinIO client from application settings."""
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket_exists(client: Minio, bucket: str) -> None:
    """Create `bucket` if it does not already exist.

    Idempotent — safe to call on every startup. Runs synchronously; callers
    that need async behaviour should wrap in `asyncio.to_thread`.
    """
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

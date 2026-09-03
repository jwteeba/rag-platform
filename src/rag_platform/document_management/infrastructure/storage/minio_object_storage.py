"""MinIO-backed implementation of `ObjectStoragePort`.

The MinIO Python SDK is synchronous. Every method here wraps the blocking
call in `asyncio.to_thread` so the event loop is never blocked — the same
pattern used throughout the codebase for any sync I/O that can't be made
async natively.
"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from typing import TYPE_CHECKING

from rag_platform.document_management.domain.ports import ObjectStoragePort

if TYPE_CHECKING:
    from minio import Minio


class MinioObjectStorage(ObjectStoragePort):
    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        def _put() -> None:
            self._client.put_object(
                self._bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self._bucket, key)

    async def read(self, key: str) -> bytes:
        def _get() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(_get)

    async def presigned_download_url(self, key: str, *, expiry_seconds: int) -> str:
        def _presign() -> str:
            return self._client.presigned_get_object(
                self._bucket, key, expires=timedelta(seconds=expiry_seconds)
            )

        return await asyncio.to_thread(_presign)

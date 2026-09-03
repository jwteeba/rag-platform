"""Integration tests for `MinioObjectStorage`.

Uses moto's threaded server mode so the MinIO SDK (which runs in a thread
pool via `asyncio.to_thread`) can reach the mock over a real HTTP socket.
moto's context-manager mock (`@mock_aws`) is thread-local and therefore
invisible to `to_thread` workers — the server mode is the correct approach
when the code under test crosses thread boundaries.

See ADR-0008 for the disclosure on this trade-off.
"""

from __future__ import annotations

import threading

import boto3
import pytest
from moto.server import DomainDispatcherApplication, create_backend_app
from werkzeug.serving import make_server

from rag_platform.document_management.infrastructure.storage.minio_object_storage import (
    MinioObjectStorage,
)

BUCKET = "test-bucket"


@pytest.fixture(scope="module")
def moto_server():  # type: ignore[no-untyped-def]
    """Start a moto S3 server on a free port for the duration of the module."""
    app = DomainDispatcherApplication(create_backend_app)
    server = make_server("127.0.0.1", 0, app)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def s3_client(moto_server: str):  # type: ignore[no-untyped-def]
    """A boto3 S3 client pointed at the moto server, with the test bucket created."""
    endpoint = f"http://{moto_server}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=BUCKET)
    yield client
    # Clean up bucket contents after each test.
    objects = client.list_objects(Bucket=BUCKET).get("Contents", [])
    for obj in objects:
        client.delete_object(Bucket=BUCKET, Key=obj["Key"])


@pytest.fixture
def storage(moto_server: str) -> MinioObjectStorage:
    """A `MinioObjectStorage` pointed at the moto server."""
    from minio import Minio

    client = Minio(
        moto_server,
        access_key="test",
        secret_key="test",
        secure=False,
    )
    return MinioObjectStorage(client=client, bucket=BUCKET)


class TestMinioObjectStorage:
    async def test_upload_then_object_exists(self, s3_client, storage: MinioObjectStorage) -> None:  # type: ignore[no-untyped-def]
        await storage.upload("docs/file.pdf", b"hello pdf", "application/pdf")

        response = s3_client.get_object(Bucket=BUCKET, Key="docs/file.pdf")
        assert response["Body"].read() == b"hello pdf"

    async def test_delete_removes_object(self, s3_client, storage: MinioObjectStorage) -> None:  # type: ignore[no-untyped-def]
        await storage.upload("docs/file.pdf", b"data", "application/pdf")
        await storage.delete("docs/file.pdf")

        objects = s3_client.list_objects(Bucket=BUCKET).get("Contents", [])
        keys = [o["Key"] for o in objects]
        assert "docs/file.pdf" not in keys

    async def test_read_returns_object_bytes(self, storage: MinioObjectStorage) -> None:
        await storage.upload("docs/file.pdf", b"data", "application/pdf")

        assert await storage.read("docs/file.pdf") == b"data"

    async def test_presigned_url_is_a_string(self, s3_client, storage: MinioObjectStorage) -> None:  # type: ignore[no-untyped-def]
        await storage.upload("docs/file.pdf", b"data", "application/pdf")

        url = await storage.presigned_download_url("docs/file.pdf", expiry_seconds=3600)

        assert isinstance(url, str)
        assert "file.pdf" in url

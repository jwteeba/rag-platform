"""Integration coverage for eager cleanup against an S3-compatible server."""

from __future__ import annotations

import threading

import boto3
import pytest
from moto.server import DomainDispatcherApplication, create_backend_app
from werkzeug.serving import make_server

from rag_platform.core.celery import celery_app
from rag_platform.document_management.tasks.storage_cleanup import cleanup_storage_object


@pytest.fixture
def moto_server():  # type: ignore[no-untyped-def]
    app = DomainDispatcherApplication(create_backend_app)
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def s3_client(moto_server: str):  # type: ignore[no-untyped-def]
    client = boto3.client(
        "s3",
        endpoint_url=f"http://{moto_server}",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    client.create_bucket(Bucket="test-bucket")
    return client


def test_cleanup_task_removes_orphaned_minio_object(
    monkeypatch, s3_client, moto_server  # type: ignore[no-untyped-def]
) -> None:
    """An object with already-deleted metadata is eventually removed."""
    from rag_platform.core.config import Settings

    settings = Settings(
        minio_endpoint=moto_server,
        minio_access_key="test",
        minio_secret_key="test",
        minio_secure=False,
        minio_bucket="test-bucket",
    )
    monkeypatch.setattr(
        "rag_platform.document_management.tasks.storage_cleanup.get_settings", lambda: settings
    )
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    s3_client.put_object(Bucket="test-bucket", Key="documents/orphan.pdf", Body=b"orphan")

    cleanup_storage_object.delay("documents/orphan.pdf").get()

    objects = s3_client.list_objects(Bucket="test-bucket").get("Contents", [])
    keys = [item["Key"] for item in objects]
    assert "documents/orphan.pdf" not in keys

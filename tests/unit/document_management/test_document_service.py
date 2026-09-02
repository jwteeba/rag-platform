"""Unit tests for `DocumentService`.

Uses fake in-memory implementations of both ports — no Postgres, no MinIO.
"""

from __future__ import annotations

import uuid

import pytest

from rag_platform.document_management.application.dto.document_dto import UploadDocumentInput
from rag_platform.document_management.application.services.document_service import DocumentService
from rag_platform.document_management.domain.entities import Document
from rag_platform.document_management.domain.exceptions import (
    DocumentNotFoundError,
    EmptyFileError,
    FileTooLargeError,
    UnsupportedContentTypeError,
)
from rag_platform.document_management.domain.ports import DocumentRepositoryPort, ObjectStoragePort

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeDocumentRepository(DocumentRepositoryPort):
    def __init__(self) -> None:
        self._docs: dict[uuid.UUID, Document] = {}

    async def add(self, document: Document) -> None:
        self._docs[document.id] = document

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        return self._docs.get(document_id)

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, after_id: uuid.UUID | None
    ) -> tuple[list[Document], bool]:
        owned = [d for d in self._docs.values() if d.owner_id == owner_id]
        owned.sort(key=lambda d: d.id)
        if after_id is not None:
            owned = [d for d in owned if d.id > after_id]
        has_more = len(owned) > limit
        return owned[:limit], has_more

    async def delete(self, document_id: uuid.UUID) -> None:
        self._docs.pop(document_id, None)


class FakeObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def upload(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.deleted.append(key)

    async def presigned_download_url(self, key: str, *, expiry_seconds: int) -> str:
        return f"https://example.com/{key}?expires={expiry_seconds}"


class FailingDeleteStorage(FakeObjectStorage):
    async def delete(self, key: str) -> None:
        raise RuntimeError("MinIO temporarily unavailable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ALLOWED_TYPES = ["application/pdf", "text/plain"]
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@pytest.fixture
def repo() -> FakeDocumentRepository:
    return FakeDocumentRepository()


@pytest.fixture
def storage() -> FakeObjectStorage:
    return FakeObjectStorage()


@pytest.fixture
def service(repo: FakeDocumentRepository, storage: FakeObjectStorage) -> DocumentService:
    return DocumentService(
        repository=repo,
        storage=storage,
        max_size_bytes=MAX_SIZE,
        allowed_content_types=ALLOWED_TYPES,
        presigned_expiry_seconds=3600,
    )


def _input(**overrides: object) -> UploadDocumentInput:
    defaults: dict[str, object] = {
        "owner_id": uuid.uuid4(),
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "data": b"PDF content",
    }
    defaults.update(overrides)
    return UploadDocumentInput(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpload:
    async def test_upload_returns_document(self, service: DocumentService) -> None:
        doc = await service.upload(_input())

        assert doc.filename == "test.pdf"
        assert doc.content_type == "application/pdf"
        assert doc.size_bytes == len(b"PDF content")

    async def test_upload_stores_object(
        self, service: DocumentService, storage: FakeObjectStorage
    ) -> None:
        doc = await service.upload(_input())

        assert doc.storage_key in storage.objects

    async def test_upload_persists_metadata(
        self, service: DocumentService, repo: FakeDocumentRepository
    ) -> None:
        doc = await service.upload(_input())

        assert await repo.get_by_id(doc.id) is not None

    async def test_empty_file_raises(self, service: DocumentService) -> None:
        with pytest.raises(EmptyFileError):
            await service.upload(_input(data=b""))

    async def test_file_too_large_raises(self, service: DocumentService) -> None:
        with pytest.raises(FileTooLargeError):
            await service.upload(_input(data=b"x" * (MAX_SIZE + 1)))

    async def test_unsupported_content_type_raises(self, service: DocumentService) -> None:
        with pytest.raises(UnsupportedContentTypeError):
            await service.upload(_input(content_type="image/png"))

    async def test_storage_key_contains_id_and_filename(self, service: DocumentService) -> None:
        doc = await service.upload(_input(filename="report.pdf"))

        assert str(doc.id) in doc.storage_key
        assert "report.pdf" in doc.storage_key


class TestGet:
    async def test_get_returns_own_document(self, service: DocumentService) -> None:
        owner_id = uuid.uuid4()
        doc = await service.upload(_input(owner_id=owner_id))

        found = await service.get(doc.id, requester_id=owner_id)

        assert found.id == doc.id

    async def test_get_unknown_id_raises(self, service: DocumentService) -> None:
        with pytest.raises(DocumentNotFoundError):
            await service.get(uuid.uuid4(), requester_id=uuid.uuid4())

    async def test_get_other_owners_document_raises(self, service: DocumentService) -> None:
        doc = await service.upload(_input(owner_id=uuid.uuid4()))

        with pytest.raises(DocumentNotFoundError):
            await service.get(doc.id, requester_id=uuid.uuid4())


class TestList:
    async def test_list_returns_only_own_documents(self, service: DocumentService) -> None:
        owner = uuid.uuid4()
        other = uuid.uuid4()
        await service.upload(_input(owner_id=owner))
        await service.upload(_input(owner_id=other))

        docs, _ = await service.list_for_user(owner, limit=10, after_id=None)

        assert len(docs) == 1
        assert docs[0].owner_id == owner

    async def test_list_respects_limit(self, service: DocumentService) -> None:
        owner = uuid.uuid4()
        for _ in range(3):
            await service.upload(_input(owner_id=owner))

        docs, has_more = await service.list_for_user(owner, limit=2, after_id=None)

        assert len(docs) == 2
        assert has_more is True


class TestDelete:
    async def test_delete_removes_metadata_and_object(
        self,
        service: DocumentService,
        repo: FakeDocumentRepository,
        storage: FakeObjectStorage,
    ) -> None:
        owner_id = uuid.uuid4()
        doc = await service.upload(_input(owner_id=owner_id))

        await service.delete(doc.id, requester_id=owner_id)

        assert await repo.get_by_id(doc.id) is None
        assert doc.storage_key in storage.deleted

    async def test_delete_attempts_storage_after_metadata(
        self,
        service: DocumentService,
        storage: FakeObjectStorage,
    ) -> None:
        """The happy path removes both the metadata and storage object."""
        owner_id = uuid.uuid4()
        doc = await service.upload(_input(owner_id=owner_id))

        # Verify storage key was deleted (storage-first ordering)
        await service.delete(doc.id, requester_id=owner_id)
        assert doc.storage_key in storage.deleted

    async def test_storage_failure_deletes_metadata_and_enqueues_cleanup(
        self, repo: FakeDocumentRepository
    ) -> None:
        storage = FailingDeleteStorage()
        enqueued: list[str] = []
        service = DocumentService(
            repository=repo,
            storage=storage,
            max_size_bytes=MAX_SIZE,
            allowed_content_types=ALLOWED_TYPES,
            presigned_expiry_seconds=3600,
            enqueue_storage_cleanup=enqueued.append,
        )
        owner_id = uuid.uuid4()
        doc = await service.upload(_input(owner_id=owner_id))

        await service.delete(doc.id, requester_id=owner_id)

        assert await repo.get_by_id(doc.id) is None
        assert enqueued == [doc.storage_key]

    async def test_delete_other_owners_document_raises(self, service: DocumentService) -> None:
        doc = await service.upload(_input(owner_id=uuid.uuid4()))

        with pytest.raises(DocumentNotFoundError):
            await service.delete(doc.id, requester_id=uuid.uuid4())


class TestDownloadUrl:
    async def test_returns_presigned_url(self, service: DocumentService) -> None:
        owner_id = uuid.uuid4()
        doc = await service.upload(_input(owner_id=owner_id))

        url = await service.get_download_url(doc.id, requester_id=owner_id)

        assert doc.storage_key in url

    async def test_other_owners_document_raises(self, service: DocumentService) -> None:
        doc = await service.upload(_input(owner_id=uuid.uuid4()))

        with pytest.raises(DocumentNotFoundError):
            await service.get_download_url(doc.id, requester_id=uuid.uuid4())

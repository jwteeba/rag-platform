# ADR-0008 — Object Storage: MinIO (S3-compatible)

**Date:** 2026-09-01
**Status:** Accepted
**Phase:** 5 — Document upload

---

## Context

Phase 5 introduces document upload. Uploaded files must be stored somewhere
durable, outside the Postgres database (BLOBs in Postgres are an anti-pattern
at any meaningful file size). The requirements are:

- S3-compatible API so the adapter can be swapped for AWS S3, GCS, or any
  other provider without changing application code.
- Self-hostable for local development and CI without cloud credentials.
- Presigned URL support so clients can download directly without proxying
  bytes through the API server.

---

## Decision

**Use MinIO** as the object store, accessed via the official `minio` Python
SDK, behind an `ObjectStoragePort` interface.

---

## Flagged decisions and rationale

### Sync SDK wrapped in `asyncio.to_thread`

The `minio` SDK is synchronous. Rather than pulling in an async S3 client
(e.g. `aiobotocore`), every blocking call is wrapped in `asyncio.to_thread`.
This keeps the dependency surface small and the adapter simple. The upload
path is not on the hot path (it's a user-initiated, infrequent action), so
the thread-pool overhead is acceptable. If throughput becomes a concern, the
adapter can be swapped for an async client behind the same port without
touching any other layer.

### No `workspace_id` on documents (yet)

Per `docs/architecture.md`, workspace scoping applies to workspace-owned
resources. No workspace concept exists yet. Documents are scoped to
`owner_id` (the uploading user) for now. When workspaces are introduced, a
`workspace_id` column and composite index will be added in a migration —
the port interface and service layer will need updating at that point, but
the storage adapter will not.

### Delete ordering: storage before metadata

`DocumentService.delete` removes the object from MinIO *before* deleting the
metadata row from Postgres. If the storage delete fails, the metadata row
survives and the document remains accessible — a consistent, recoverable
state. The reverse (delete row first, storage fails) would leave an orphaned
object with no metadata, which is harder to detect and clean up.

### Signed-URL redirects (`GET /documents/{id}/download` → 307)

The download endpoint issues a 307 redirect to a presigned MinIO URL rather
than proxying the bytes. This keeps the API server out of the data path for
large files. A separate `GET /documents/{id}/download-url` endpoint returns
the URL as JSON for clients that need it programmatically (e.g. to pass to a
background job) without following a redirect.

### Uniform 404 for ownership violations

`DocumentService.get` returns `DocumentNotFoundError` (→ 404) when a
document exists but belongs to a different user, rather than a 403. This
avoids leaking which document IDs are valid for other accounts — the same
pattern used by `SessionNotFoundError` in `identity_access`.

### moto as dev/CI stand-in for MinIO

Integration tests for `MinioObjectStorage` use moto's S3 mock rather than a
real MinIO container. moto speaks the same S3 protocol the MinIO SDK uses, so
the adapter is exercised end-to-end. The trade-off: moto does not exercise
MinIO-specific behaviour (bucket policies, lifecycle rules, etc.) — none of
which this application uses. A real MinIO container is used in `make test`
(via Docker Compose) and in `make docker-up` for full end-to-end local
testing.

---

## Consequences

- `core/storage.py` provides `build_minio_client()` and
  `ensure_bucket_exists()`, mirroring `core/db.py` and `core/cache.py`.
- `document_management/infrastructure/storage/minio_object_storage.py`
  implements `ObjectStoragePort` with `asyncio.to_thread` wrapping.
- `di/containers.py` holds a `minio_client` singleton (safe — the MinIO
  client is stateless and thread-safe).
- `ensure_storage_bucket()` is called at startup (lifespan) to create the
  bucket if it doesn't exist.
- `/health/ready` gains a `storage` check (bucket reachability via
  `bucket_exists`).
- CI starts MinIO via `docker run` (not `services:`, which can't override
  the command) and creates the test bucket with `mc mb` before `pytest`.

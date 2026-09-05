# ADR-0012 — Vector Store: Qdrant Collection Schema

**Date:** 2026-09-03
**Status:** Accepted
**Phase:** 8 — Embeddings + Vector Storage

## Context

ADR-0002 already decided to use Qdrant as the vector database. This ADR
records the collection schema decisions made when actually implementing it
in Phase 8.

## Decisions

### Collection name and vector configuration

A single collection (`APP_QDRANT_COLLECTION_NAME`, default `rag_platform`)
holds all chunks for all users. Cosine distance is used because embedding
models are trained to produce unit-normalised vectors where cosine similarity
is the natural similarity measure.

Vector dimensions are configurable (`APP_EMBEDDING_DIMENSIONS`) and must
match the embedding model. The collection is created once at startup
(`ensure_collection_exists`, called from the lifespan hook alongside
`ensure_bucket_exists`) and never recreated automatically — changing the
model requires a manual collection drop and re-index.

### Point ID

Each Qdrant point uses the chunk's UUID (`chunk.id`) as its point ID,
stored as a string. This makes the Postgres `chunks.embedding_id` column
redundant for lookup purposes, but it is kept as a convenience for
cross-referencing and for confirming that a chunk has been indexed without
querying Qdrant.

### Payload fields

Every point carries four payload fields:

| Field | Type | Purpose |
|---|---|---|
| `document_id` | string (UUID) | Link back to the source document |
| `chunk_id` | string (UUID) | Redundant with point ID; convenience for payload-only reads |
| `owner_id` | string (UUID) | **Ownership filter for Phase 11 retrieval** |
| `chunk_index` | integer | Ordering within the document for result presentation |

`owner_id` is stored on every point so that Phase 11's hybrid search can
apply a Qdrant payload filter (`must: [{key: "owner_id", match: {value: "..."}}]`)
without a round-trip to Postgres. This is the primary reason payload is
stored at all at this phase.

### `embedding_status` in Postgres

`chunks.embedding_status` (`pending` → `indexed` | `failed`) mirrors the
document's own `status` column. It lets the API surface indexing progress
per-chunk without querying Qdrant, and lets a future re-indexing job
identify chunks that need to be re-embedded after a model change.

## Consequences

- Changing `APP_EMBEDDING_DIMENSIONS` after data has been indexed is a
  breaking change: the existing collection must be deleted and all chunks
  re-embedded.
- Multi-tenancy filtering in Phase 11 relies on `owner_id` being present on
  every point. Any backfill or re-index job must preserve this field.
- A single collection for all users is simpler to operate than per-user
  collections and is the standard Qdrant multi-tenancy pattern for this
  scale. Per-user collections would be considered only if isolation
  requirements (e.g. regulatory) demanded it.

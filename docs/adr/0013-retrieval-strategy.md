# ADR-0013 — Retrieval Strategy: Vector Search, Owner Filtering, Score Threshold, Re-ranking

**Status:** Accepted
**Date:** 2026-09-20
**Phase:** 9

---

## Context

Phase 9 adds the "R" in RAG: given a user query, find the most semantically
relevant chunks from that user's indexed documents and return them with source
attribution. The retrieval pipeline must be:

- **Correct** — results must only ever come from the requesting user's own documents.
- **Meaningful** — similarity scores must be comparable to the scores produced at
  index time (Phase 8), because both use the same embedding model and the same
  Qdrant cosine-distance collection.
- **Extensible** — the architecture must accommodate optional re-ranking without
  restructuring the service layer.

---

## Decisions

### 1. Vector-first retrieval via Qdrant

Query text is embedded with the same `EmbeddingPort` adapter used at index time
(same model, same normalisation). The resulting vector is sent to Qdrant's
`search` endpoint, which returns the top-`k` nearest neighbours by cosine
similarity. This is the standard ANN (approximate nearest-neighbour) approach
and is the correct first stage for any RAG pipeline.

`RetrievalService` depends on `EmbeddingPort` (the domain port), not a concrete
adapter — the same swappability guarantee as Phase 8.

### 2. Owner-ID filter applied inside Qdrant, not post-filter

Every Qdrant query carries a `must` filter on `owner_id`. This is a **pre-filter**
(Qdrant evaluates it before scoring), not a post-filter applied in Python after
results are returned.

**Why pre-filter matters:**

- A post-filter approach would ask Qdrant for `limit` results, then discard those
  belonging to other users, potentially returning fewer than `limit` results (or
  zero) even when the user has many matching chunks.
- A pre-filter guarantees that the `limit` is honoured correctly: Qdrant only
  considers the requesting user's vectors during the ANN search.
- It is also the correct security boundary: a user supplying a known `document_id`
  belonging to another user will receive zero results, not a filtered subset —
  the ownership check is structural, not advisory.

`owner_id` is stored as a Qdrant point payload field (set at upsert time in
Phase 8's `embed_chunks` task) and is indexed implicitly by Qdrant's payload
filtering.

### 3. Score threshold

Results below `APP_SEARCH_SCORE_THRESHOLD` (default `0.7`) are dropped by
Qdrant before they reach the application. This prevents low-quality, semantically
unrelated chunks from appearing in results.

`0.7` is a reasonable default for cosine similarity with `text-embedding-3-small`
(OpenAI) and `all-MiniLM-L6-v2` (local). Operators can lower it for recall-heavy
use cases or raise it for precision-heavy ones via the environment variable.

### 4. Re-ranking deferred

Cross-encoder re-ranking (e.g. a small local `cross-encoder/ms-marco-MiniLM-L-6-v2`
model) would improve precision for ambiguous queries by scoring each
(query, chunk) pair jointly rather than independently. It is **not implemented
in Phase 9** for the following reasons:

- It requires a second model download and adds latency on every search request.
- The score-threshold filter already removes the worst results.
- The primary value of re-ranking is in the generation phase (Phase 10), where
  the top-k chunks are passed to an LLM — a small improvement in chunk ordering
  has diminishing returns until the generation prompt is also tuned.

The `APP_RETRIEVAL_RERANKING_ENABLED` flag is wired into `Settings` and
`RetrievalService` is structured to accept a future `RerankerPort` without
changing its public interface. When re-ranking is implemented, it will be
added as an optional second stage between vector search and result hydration,
controlled by this flag.

---

## Consequences

- Every search request embeds the query synchronously in the API worker. For
  OpenAI this is a network call; for the local adapter it is a CPU call. Both
  are fast enough for interactive use but should be monitored under load.
- The `owner_id` payload field must be present on every Qdrant point. Points
  upserted without it (e.g. by a buggy migration) will never appear in search
  results — a safe failure mode.
- Lowering `search_score_threshold` to `0.0` disables score filtering entirely,
  which is useful for integration tests that use synthetic low-dimensional vectors.

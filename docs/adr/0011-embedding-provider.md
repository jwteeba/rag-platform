# ADR-0011 — Embedding Provider: OpenAI as Default, Local Model as Swap-in

**Date:** 2026-09-03
**Status:** Accepted
**Phase:** 8 — Embeddings + Vector Storage

## Context

Phase 8 requires converting text chunks into dense vector embeddings. Two
realistic options exist for a project at this stage:

1. **OpenAI Embeddings API** (`text-embedding-3-small` / `text-embedding-3-large`) —
   hosted, no GPU required, state-of-the-art quality, pay-per-token.
2. **Local sentence-transformers** (e.g. `all-MiniLM-L6-v2`) — runs in-process,
   no API key, no per-call cost, lower quality, requires CPU/GPU resources in
   the container.

The `EmbeddingPort` protocol in `indexing/domain/ports.py` was introduced
specifically so this choice is a one-line config change, not a code change.

## Decision

**OpenAI is the default** (`APP_EMBEDDING_PROVIDER=openai`,
`APP_EMBEDDING_MODEL=text-embedding-3-small`, 1536 dimensions).

**`SentenceTransformerEmbeddingAdapter`** is shipped alongside it as a
fully-supported swap-in, activated by `APP_EMBEDDING_PROVIDER=local`. Both
implement the same `EmbeddingPort` protocol; no application or domain code
changes when switching.

## Rationale

- `text-embedding-3-small` consistently outperforms open models of comparable
  size on MTEB benchmarks while being cheap enough for a development/prototype
  workload.
- The local adapter removes the OpenAI dependency entirely for air-gapped or
  cost-sensitive deployments — the only required change is two env vars
  (`APP_EMBEDDING_PROVIDER=local`, `APP_EMBEDDING_MODEL=<model-name>`,
  `APP_EMBEDDING_DIMENSIONS=<dim>`).
- Shipping both adapters now means the swap is tested and documented before
  production load makes it expensive to change.

## Consequences

- `APP_OPENAI_API_KEY` must be set when `APP_EMBEDDING_PROVIDER=openai` in
  production; the app validates this at startup.
- `APP_EMBEDDING_DIMENSIONS` must match the model in use. Changing the model
  after data has been indexed requires re-creating the Qdrant collection and
  re-embedding all chunks (the collection's vector size is fixed at creation).
- The `sentence-transformers` package is a heavy dependency (~500 MB with
  PyTorch). It is included unconditionally in `pyproject.toml` for simplicity;
  a future optimisation could make it optional.

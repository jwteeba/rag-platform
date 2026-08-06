# 0002. Vector store: Qdrant instead of ChromaDB

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

Phase 0 flagged ChromaDB's clustering/HA maturity as a risk for an
enterprise-scale deployment, and proposed isolating the vector store behind
a `VectorIndexPort` interface (`indexing/domain/ports.py`) specifically so
this decision could be revisited cheaply.

## Decision

Use Qdrant as the vector database, implemented in Phase 9 behind
`VectorIndexPort`. No other phase depends on the concrete vector store —
`Indexing` and `Retrieval` application services depend only on the port.

## Consequences

- The Phase 0 repository layout, dependency graph, and layering rules are
  unaffected — `indexing/infrastructure/` will contain a Qdrant adapter
  instead of a Chroma adapter when Phase 9 is implemented.
- `docker-compose.yml` will gain a `qdrant` service in Phase 9 (Phase 1's
  compose file intentionally has no vector-store service yet — see that
  file's header comment).
- No action needed in Phases 1–8; this ADR exists purely to record the
  decision at the time it was made, per the project's "explain important
  architectural decisions" requirement.

# Architecture

This is the living version of the Phase 0 planning document, updated with
decisions confirmed since. See `docs/adr/` for the reasoning behind each
individual decision as it was made.

## Bounded contexts

| Context | Responsibility |
|---|---|
| **IdentityAccess** | Users, workspaces, roles, permissions, auth tokens |
| **DocumentManagement** | Upload, storage, metadata, ingestion pipeline state |
| **Indexing** | Chunking, embedding, vector index, lexical index |
| **Retrieval** | Hybrid search, filtering, reranking |
| **Generation** | LLM gateway, prompt construction, chat/conversation, citations |

A sixth, **Platform**, is cross-cutting (observability, background jobs,
caching, storage, health) and owns no domain data.

Built as a modular monolith (ADR-0001): one deployable, strict internal
boundaries enforced by directory structure.

## Layering (per bounded context)

```
API  →  Application  →  Domain  ←  Infrastructure
```

- **API**: FastAPI routers. Thin — parse request, call one application
  service method, map result to response schema. No I/O, no business logic.
- **Application**: use-case orchestration. Depends on Domain ports, never on
  concrete Infrastructure classes.
- **Domain**: entities, value objects, domain rules, port interfaces. Zero
  framework imports.
- **Infrastructure**: implements Domain ports (repositories, external
  providers). Depends outward on real libraries (SQLAlchemy, Qdrant client,
  OpenAI SDK, etc.).

## Context-level dependencies

- `IdentityAccess` has no outbound dependency on any other context.
- `Indexing` depends on `DocumentManagement`, not vice versa.
- `Retrieval` depends on `Indexing`'s output only.
- `Generation` depends on `Retrieval` and `IdentityAccess`.
- `Platform` is a dependency leaf — everyone may depend on it; it depends on
  nothing context-specific.

## Confirmed decisions since Phase 0

| Question | Decision | ADR |
|---|---|---|
| Vector store | **Qdrant**, not ChromaDB — behind `VectorIndexPort` | [0002](adr/0002-vector-store-qdrant.md) |
| Deployment target | **Platform-agnostic** — standard Dockerfile, no PaaS-specific manifest in this repo | [0003](adr/0003-deployment-target-render.md) (superseded), [0004](adr/0004-deployment-target-platform-agnostic.md) |
| Multi-tenancy | **Single shared schema, `workspace_id` scoping** | (applied directly in Phase 3 domain models — no dedicated ADR needed, it's a straightforward default rather than a reversal of an earlier plan) |

The multi-tenancy choice means every tenant-scoped table (documents, chunks,
conversations, etc., starting Phase 3) carries a `workspace_id` column with
a composite index, and every repository query is required to filter by it —
enforced via a base repository method rather than left to each call site to
remember.

## Repository layout

```
rag-platform/
├── pyproject.toml
├── poetry.lock
├── README.md
├── Makefile
├── docker-compose.yml
├── docker-compose.override.yml
├── Dockerfile
├── .env.example
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── docs/
│   ├── adr/
│   └── architecture.md
├── src/rag_platform/
│   ├── main.py                 # FastAPI app factory
│   ├── core/                   # Shared/Core — no downward deps
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   ├── errors.py           # RFC 7807
│   │   └── middleware/
│   ├── platform/
│   │   └── health/             # Phase 1. cache/, queue/, storage/,
│   │                           # eventbus/ arrive in Phases 4, 5, 15
│   └── <bounded contexts>/     # identity_access, document_management,
│                               # indexing, retrieval, generation —
│                               # added starting Phase 2
└── tests/
    ├── unit/
    ├── integration/
    ├── api/
    └── factories/
```

Bounded-context packages not yet created (`identity_access/`,
`document_management/`, `indexing/`, `retrieval/`, `generation/`) will each
mirror the four-layer structure exactly when their phase arrives.

## Cross-cutting conventions

- **Errors**: RFC 7807 `application/problem+json`, produced by a single
  `ErrorHandlingMiddleware` — no route constructs error JSON itself.
- **IDs**: UUIDv7 for all primary keys (from Phase 3 onward).
- **Request/Correlation IDs**: `RequestIDMiddleware` / `CorrelationIDMiddleware`
  generate-or-propagate `X-Request-ID` / `X-Correlation-ID`, bound into every
  `structlog` log line via contextvars.
- **Config**: one `Settings` class, `pydantic-settings`, `APP_`-prefixed env
  vars. No module reads `os.environ` directly outside `core/config.py`.
- **Testing**: every service gets a unit test against mocked ports; every
  route gets an API test. Nothing merges without `make check` passing.

## Phase status

- **Phase 0** — Planning & architecture. Complete.
- **Phase 1** — Repo scaffold, config, logging, health, lint/format/type,
  tests, CI. Complete (this document reflects it).
- **Phase 2+** — Not started. See the phase list in the original project
  brief; each phase's own PR/commit will update this document as it lands.

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
| IdentityAccess persistence (Phase 2) | **In-memory**, behind `UserRepositoryPort` / `RefreshTokenStorePort` — swapped for Postgres in Phase 3 | [0005](adr/0005-in-memory-persistence-for-phase-2-auth.md) |
| RBAC model (Phase 2) | **Fixed two roles** (ADMIN, MEMBER); permissions (not roles) are what's checked everywhere, so dynamic roles later is a contained change | [0005](adr/0005-in-memory-persistence-for-phase-2-auth.md) |

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
│   │   ├── security.py         # Phase 2: bcrypt + JWT primitives
│   │   ├── pagination.py       # Phase 2: cursor pagination
│   │   └── middleware/
│   ├── platform/
│   │   └── health/             # Phase 1. cache/, queue/, storage/,
│   │                           # eventbus/ arrive in Phases 4, 5, 15
│   ├── identity_access/        # Phase 2: auth, users, RBAC
│   │   ├── api/v1/             # auth_router, users_router, dependencies
│   │   ├── application/        # AuthenticationService, UserService
│   │   ├── domain/              # User entity, Role/Permission, ports
│   │   └── infrastructure/     # bcrypt/JWT adapters, in-memory repos
│   ├── di/                     # Phase 2: DI container wiring
│   └── <other contexts>/       # document_management, indexing,
│                               # retrieval, generation — later phases
└── tests/
    ├── unit/
    ├── integration/
    ├── api/
    └── factories/
```

Bounded-context packages not yet created (`document_management/`,
`indexing/`, `retrieval/`, `generation/`) will each mirror the four-layer
structure exactly when their phase arrives — `identity_access/` (Phase 2) is
the reference example of that structure in practice.

## Cross-cutting conventions

- **Errors**: RFC 7807 `application/problem+json`, produced by
  `ErrorHandlingMiddleware` for our own exceptions *and* by explicit
  `app.add_exception_handler` registrations for FastAPI/Starlette's built-in
  `HTTPException` and `RequestValidationError` — the latter two are
  intercepted by Starlette's own exception handling before they'd reach our
  middleware, so they need separate handlers to stay RFC 7807 too (see
  `core/middleware/error_handling.py`). No route constructs error JSON
  itself either way.
- **IDs**: UUIDv7 for all primary keys (from Phase 3 onward; Phase 2's
  in-memory `User.id` uses UUIDv4 since there's no index-locality benefit
  without a real database yet).
- **Request/Correlation IDs**: `RequestIDMiddleware` / `CorrelationIDMiddleware`
  generate-or-propagate `X-Request-ID` / `X-Correlation-ID`, bound into every
  `structlog` log line via contextvars.
- **Config**: one `Settings` class, `pydantic-settings`, `APP_`-prefixed env
  vars. No module reads `os.environ` directly outside `core/config.py`. As
  of Phase 2, `Settings` also refuses to start in production with the
  default JWT signing secret still in place.
- **AuthN/AuthZ**: JWT bearer tokens (`Authorization: Bearer <token>`),
  validated by `identity_access`'s `get_current_user` FastAPI dependency.
  Permission checks are declarative at the route decorator
  (`Depends(require_permission(Permission.X))`), never branching inside a
  route body.
- **Pagination**: cursor-based, implemented once in `core/pagination.py`
  (`Page[T]`, `encode_cursor`/`decode_cursor`), reused by every list
  endpoint — `GET /users` (Phase 2) is the first consumer.
- **Testing**: every service gets a unit test against mocked or in-memory
  ports; every route gets an API test. Nothing merges without `make check`
  passing.

## Phase status

- **Phase 0** — Planning & architecture. Complete.
- **Phase 1** — Repo scaffold, config, logging, health, lint/format/type,
  tests, CI. Complete.
- **Phase 2** — Authentication: OAuth2 password flow, JWT access/refresh
  tokens with rotation, RBAC (fixed ADMIN/MEMBER roles + permissions), user
  registration and self-service profile management, admin user management.
  In-memory persistence (see ADR-0005) — Phase 3 swaps in Postgres behind
  the same ports. Complete (this document reflects it).
- **Phase 3+** — Not started. See the phase list in the original project
  brief; each phase's own PR/commit will update this document as it lands.

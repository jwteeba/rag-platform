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
| IdentityAccess persistence | **In-memory adapters (Phase 2, ADR-0005)** still shipped and unit-tested; **Postgres adapters (Phase 3, ADR-0006)** are what the running application actually uses, behind the same `UserRepositoryPort` / `RefreshTokenStorePort` | [0005](adr/0005-in-memory-persistence-for-phase-2-auth.md), [0006](adr/0006-postgres-persistence-identity-access.md) |
| RBAC model | **Fixed two roles** (ADMIN, MEMBER); permissions (not roles) are what's checked everywhere, so dynamic roles later is a contained change | [0005](adr/0005-in-memory-persistence-for-phase-2-auth.md) |

The multi-tenancy choice means every tenant-*owned* table (documents,
chunks, conversations, etc., in later phases) will carry a `workspace_id`
column with a composite index, with every repository query required to
filter by it. `users` is deliberately **not** such a table — see
ADR-0006 — so Phase 3 hasn't exercised this convention yet; it remains a
forward-looking rule for the phase that introduces the first
workspace-owned resource.

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
├── alembic.ini
├── alembic/
│   ├── env.py                   # async, reads APP_DATABASE_URL from Settings
│   ├── script.py.mako
│   └── versions/
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
│   │   ├── security.py         # bcrypt + JWT primitives
│   │   ├── pagination.py       # cursor pagination
│   │   ├── ids.py              # Phase 3: UUIDv7 generation
│   │   ├── db.py               # Phase 3: SQLAlchemy Base, mixins, engine
│   │   └── middleware/
│   ├── platform/
│   │   ├── health/              # real DB connectivity check as of Phase 3
│   │   └── database/            # Phase 3: get_db_session FastAPI dependency
│   │                            # cache/, queue/, storage/, eventbus/
│   │                            # arrive in Phases 4, 5, 15
│   ├── identity_access/        # auth, users, RBAC
│   │   ├── api/v1/             # auth_router, users_router, dependencies
│   │   ├── application/        # AuthenticationService, UserService
│   │   ├── domain/              # User entity, Role/Permission, ports
│   │   └── infrastructure/     # bcrypt/JWT adapters; in-memory repos
│   │                            # (Phase 2) AND Postgres repos (Phase 3),
│   │                            # both implementing the same ports
│   ├── di/                     # DI container wiring
│   └── <other contexts>/       # document_management, indexing,
│                               # retrieval, generation — later phases
└── tests/
    ├── unit/                   # no DB dependency — in-memory adapters only
    ├── integration/            # Phase 3: real Postgres (di container,
    │                           # Postgres repositories)
    ├── api/                    # full app, real Postgres as of Phase 3
    └── factories/
```

Bounded-context packages not yet created (`document_management/`,
`indexing/`, `retrieval/`, `generation/`) will each mirror the four-layer
structure exactly when their phase arrives — `identity_access/` is the
reference example of that structure in practice, now with two working
Infrastructure adapters (in-memory, Postgres) for the same two ports as a
concrete demonstration of why the port/adapter boundary is drawn where it
is.

## Cross-cutting conventions

- **Errors**: RFC 7807 `application/problem+json`, produced by
  `ErrorHandlingMiddleware` for our own exceptions *and* by explicit
  `app.add_exception_handler` registrations for FastAPI/Starlette's built-in
  `HTTPException` and `RequestValidationError` — the latter two are
  intercepted by Starlette's own exception handling before they'd reach our
  middleware, so they need separate handlers to stay RFC 7807 too (see
  `core/middleware/error_handling.py`). No route constructs error JSON
  itself either way.
- **IDs**: UUIDv7 for all primary keys, generated application-side via
  `core/ids.py` (the `uuid6` package — stdlib `uuid` doesn't gain `uuid7()`
  until Python 3.14). The in-memory adapters' `User.create()` uses the same
  generator, so ids are UUIDv7 regardless of which adapter is wired in.
- **Request/Correlation IDs**: `RequestIDMiddleware` / `CorrelationIDMiddleware`
  generate-or-propagate `X-Request-ID` / `X-Correlation-ID`, bound into every
  `structlog` log line via contextvars.
- **Config**: one `Settings` class, `pydantic-settings`, `APP_`-prefixed env
  vars. No module reads `os.environ` directly outside `core/config.py`.
  `Settings` refuses to start in production with the default JWT signing
  secret still in place.
- **Database sessions**: one `AsyncSession` per request, opened by
  `platform/database/dependencies.py::get_db_session`, committed on success
  / rolled back on any exception. Repositories never open their own session
  — they receive one through `Depends()`. Application services that need a
  repository are themselves built per-request from that session (see
  `identity_access/api/v1/dependencies.py`), not held as process-wide
  singletons — the DI container only holds the engine, session factory, and
  genuinely stateless singletons (password hasher, token service). See
  ADR-0006 for why this changed from Phase 2's simpler singleton-service
  container.
- **AuthN/AuthZ**: JWT bearer tokens (`Authorization: Bearer <token>`),
  validated by `identity_access`'s `get_current_user` FastAPI dependency.
  Permission checks are declarative at the route decorator
  (`Depends(require_permission(Permission.X))`), never branching inside a
  route body.
- **Pagination**: cursor-based, implemented once in `core/pagination.py`
  (`Page[T]`, `encode_cursor`/`decode_cursor`), reused by every list
  endpoint — `GET /users` is the first consumer.
- **Migrations**: Alembic, async, autogenerated from `Base.metadata` (every
  bounded context's ORM models import into `alembic/env.py` so they
  register). `make db-upgrade` / `make db-revision m="..."` — see README.
- **Testing**: every service gets a unit test against mocked or in-memory
  ports; every route gets an API test; every Postgres-backed adapter gets an
  integration test against a real, isolated test database (truncated before
  each test — see `tests/conftest.py::clean_database`). Nothing merges
  without `make check` passing, and CI provisions its own disposable
  Postgres service to run it.

## Phase status

- **Phase 0** — Planning & architecture. Complete.
- **Phase 1** — Repo scaffold, config, logging, health, lint/format/type,
  tests, CI. Complete.
- **Phase 2** — Authentication: OAuth2 password flow, JWT access/refresh
  tokens with rotation, RBAC (fixed ADMIN/MEMBER roles + permissions), user
  registration and self-service profile management, admin user management.
  Complete.
- **Phase 3** — Database: SQLAlchemy 2.0 async ORM, Alembic migrations,
  Postgres-backed `UserRepositoryPort` / `RefreshTokenStorePort`
  implementations swapped in for Phase 2's in-memory adapters (ADR-0006),
  UUIDv7 primary keys, real DB connectivity check on `/health/ready`.
  Complete (this document reflects it).
- **Phase 4+** — Not started. See the phase list in the original project
  brief; each phase's own PR/commit will update this document as it lands.

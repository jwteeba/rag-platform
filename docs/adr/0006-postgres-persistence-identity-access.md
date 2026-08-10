# 0006. Postgres persistence for identity_access

- **Status:** Accepted
- **Date:** 2026-08-07

## Context

ADR-0005 (Phase 2) put `UserRepositoryPort` and `RefreshTokenStorePort`
behind in-memory adapters specifically so they could be swapped for a real
database once Phase 3 (Database: SQLAlchemy, Alembic, Repositories, Base
models) arrived, without touching `identity_access/application/` or
`identity_access/domain/`.

## Decision

Implement `PostgresUserRepository` and `PostgresRefreshTokenStore` behind
the same two ports, using SQLAlchemy 2.0's async ORM (`asyncpg` driver) and
Alembic for schema migrations. Wire them into `di/containers.py` /
`identity_access/api/v1/dependencies.py` in place of the Phase 2 in-memory
adapters.

This required one architectural change beyond "write the adapters":
**repositories moved from process-wide singletons to per-request
constructions.** Phase 2's `Container` held one `AuthenticationService` and
one `UserService` built once at startup, backed by in-memory dicts shared
safely across concurrent requests (protected by an `asyncio.Lock`). A real
database repository needs its own `AsyncSession` per request instead —
sharing one session across concurrent requests would let one request's
uncommitted writes leak into another's queries, and makes "commit on
success, rollback on failure" transaction semantics meaningless. `Container`
now holds only true process-wide singletons (the SQLAlchemy engine, the
session factory, the stateless password hasher and token service);
`identity_access/api/v1/dependencies.py` builds a fresh repository and
service per request from a session opened via
`platform/database/dependencies.py::get_db_session`, relying on FastAPI's
per-request dependency caching so the same session is shared between
`AuthenticationService` and `UserService` within one request.

Other decisions made alongside this swap:

- **UUIDv7 primary keys** (via the `uuid6` package, in `core/ids.py`),
  per the "IDs" convention in `docs/architecture.md` — generated
  application-side in `User.create()` rather than as a Postgres column
  default, so a newly-constructed entity already has its id before the
  first flush.
- **No `workspace_id` on `users`.** Per the architecture doc's multi-tenancy
  convention, workspace scoping applies to workspace-*owned* resources
  (documents, conversations, etc. — none of which exist yet), not to user
  accounts. A user's relationship to a workspace is membership, and no
  membership concept exists yet either. Revisit when it does.
- **`/health/ready` now performs a real `SELECT 1`** against Postgres and
  returns `503` (not `200`) if it fails — closing a gap explicitly flagged
  as deferred-to-Phase-3 in the Phase 1 `ReadinessResponse` docstring.
- **`refresh_tokens.jti` is the primary key**, not a separate surrogate
  UUID — the table's only access pattern is "look up by jti", so a second
  id column would be dead weight.

## Consequences

- **Data now survives process restarts and works correctly with multiple
  worker processes** — the two limitations ADR-0005 explicitly flagged as
  accepted-for-now are resolved.
- **Every API-level test now depends on a real, reachable Postgres
  database** (a dedicated `rag_platform_test` database — see
  `tests/conftest.py`), truncated before each test for isolation. Pure
  `tests/unit/*` tests that exercise ports/services directly via the
  Phase 2 in-memory adapters are unaffected and still have zero DB
  dependency — those adapters are still shipped and still tested; they're
  just no longer what's wired into the running application.
- **Local development and CI both require Postgres running** before `make
  dev` / `make test` will succeed — `docker-compose.yml` gains a `postgres`
  service for this (see the compose file's own comments for why it wasn't
  added earlier).
- The RBAC model is still the fixed two-role system from ADR-0005 — nothing
  about persistence changes that decision. Dynamic, database-backed roles
  remain a possible future phase, not something this ADR introduces.

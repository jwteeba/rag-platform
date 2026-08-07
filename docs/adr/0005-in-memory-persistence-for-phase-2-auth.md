# 0005. In-memory persistence for Phase 2 authentication

- **Status:** Accepted
- **Date:** 2026-08-06

## Context

The original phase plan places Phase 2 (Authentication: OAuth2, JWT, RBAC,
Users, Roles, Permissions) before Phase 3 (Database: SQLAlchemy, Alembic,
Repositories, Base models). Phase 2 therefore has no database to persist
users, roles, or refresh tokens against.

## Decision

Define `UserRepositoryPort` and `RefreshTokenStorePort` in
`identity_access/domain/ports.py`, and implement both with process-local,
`asyncio.Lock`-protected in-memory adapters
(`InMemoryUserRepository`, `InMemoryRefreshTokenStore`) for Phase 2. These
are complete, correct, fully-tested implementations of their ports — not
placeholders or stubs — built with the explicit intent of being replaced.

`AuthenticationService` and `UserService` (the application layer) depend
only on the ports, never on these concrete classes. The DI container
(`di/containers.py`) is the single place that binds port to adapter.

This mirrors the pattern already used for the vector store decision
(ADR-0002: `VectorIndexPort` behind which Chroma was swapped for Qdrant
before any dependent code existed).

## Consequences

- **Data does not survive a process restart.** Every user, role assignment,
  and issued refresh token is lost when the process exits. This is an
  accepted, documented limitation of Phase 2 — not an oversight — and is
  the direct consequence of building Authentication before Database in the
  phase ordering given for this project.
- **Phase 3 swaps the adapters, not the ports.** When Postgres/SQLAlchemy
  land, `identity_access/infrastructure/repositories/` gains
  `PostgresUserRepository` implementing `UserRepositoryPort`, and
  `di/containers.py` changes two lines to construct it instead of
  `InMemoryUserRepository`. No change to `identity_access/domain/`,
  `identity_access/application/`, or any route in
  `identity_access/api/`.
- **RBAC is a fixed two-role model in Phase 2** (see
  `identity_access/domain/roles.py`) rather than dynamic, database-backed
  custom roles, for the same reason: dynamic roles need persistence to be
  meaningful, and building CRUD against an in-memory store would be
  throwaway work. Permissions (not roles) are what the application and API
  layers check throughout, so making roles dynamic later only changes
  `ROLE_PERMISSIONS` and the `Role` type — no permission-check call site
  changes.
- **A bootstrap-admin mechanism was needed** (`ensure_bootstrap_admin` in
  `di/containers.py`, gated by the optional `APP_BOOTSTRAP_ADMIN_EMAIL` /
  `APP_BOOTSTRAP_ADMIN_PASSWORD` settings) because self-registration always
  assigns `Role.MEMBER`, and with no database there's no other way to reach
  the first admin-only endpoint on a fresh deployment. This becomes optional
  scaffolding once Phase 3 allows seeding an admin via a migration or
  management command instead, but is left in place regardless since it's
  also a convenient local-dev default.

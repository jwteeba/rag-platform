# RAG Platform

Enterprise-grade Retrieval-Augmented Generation service API. See
[`docs/architecture.md`](docs/architecture.md) for the full architecture and
[`docs/adr/`](docs/adr) for the history of architectural decisions.

**Current phase: Phase 2 — authentication (OAuth2 password flow, JWT access
+ refresh tokens, RBAC, user management).** Database, cache, storage, and RAG
functionality still don't exist — Phase 2 runs on an in-memory user store
(see [ADR-0005](docs/adr/0005-in-memory-persistence-for-phase-2-auth.md));
data does not survive a process restart until Phase 3 lands. See
`docs/architecture.md` §Phases for what's still ahead.

## Requirements

- Python 3.12+
- [Poetry](https://python-poetry.org/) 1.8+
- Docker + Docker Compose (for containerized runs)

## Getting started

```bash
# Install dependencies
make install

# Copy environment template and adjust as needed
cp .env.example .env

# Run with auto-reload
make dev
```

The API is now available at `http://localhost:8000`:

- `GET /health/live` — liveness probe
- `GET /health/ready` — readiness probe
- `GET /api/v1/docs` — interactive OpenAPI docs
- `GET /api/v1/openapi.json` — raw OpenAPI schema
- `POST /api/v1/auth/register` — create a user (always assigned the MEMBER role)
- `POST /api/v1/auth/login` — OAuth2 password grant (form fields `username`/`password`) → access + refresh tokens
- `POST /api/v1/auth/refresh` — rotate a refresh token for a new pair
- `POST /api/v1/auth/logout` — revoke a refresh token
- `GET /api/v1/users/me` / `PATCH /api/v1/users/me` — self-service profile
- `GET /api/v1/users`, `GET /api/v1/users/{id}`, `PATCH /api/v1/users/{id}` — admin only (`users:read` / `users:manage`)

To reach the admin-only endpoints on a fresh instance, set
`APP_BOOTSTRAP_ADMIN_EMAIL` / `APP_BOOTSTRAP_ADMIN_PASSWORD` in `.env` before
starting — see the comment in `.env.example`. Self-registration always
assigns the MEMBER role.

## Running with Docker Compose

```bash
make docker-up
```

This builds the image and starts the `api` service on `http://localhost:8000`
with live reload against your local `src/` directory. Phase 1's compose file
intentionally contains only the API service — Postgres, Redis, MinIO, Qdrant,
and OpenSearch are added in the phases that introduce each dependency.

## Development workflow

```bash
make lint        # ruff
make format      # black + ruff --fix
make typecheck    # mypy --strict
make test         # pytest with coverage
make check        # lint + typecheck + test — everything CI runs
make pre-commit-install  # install git hooks (run once)
```

All four checks (`ruff`, `black --check`, `mypy`, `pytest`) must pass before
a PR merges — this is enforced identically in `.github/workflows/ci.yml`.

## Manual smoke test

```bash
make dev
# in another terminal
curl -i http://localhost:8000/health/live
curl -i http://localhost:8000/health/ready

# register, then log in (OAuth2 password grant uses form fields, not JSON)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"AlicePass123","full_name":"Alice"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -d 'username=alice@example.com&password=AlicePass123'
# → { "access_token": "...", "refresh_token": "...", "token_type": "bearer", "expires_in": 900 }

curl http://localhost:8000/api/v1/users/me \
  -H 'Authorization: Bearer <access_token from above>'
```

Expected: health checks return `200 OK` with `X-Request-ID` and
`X-Correlation-ID` headers; register returns `201` with the new user (never
the password); login returns a token pair; `/users/me` returns that user's
profile.

Every error response — from our own domain exceptions, from FastAPI's
`OAuth2PasswordBearer` (e.g. no token supplied), and from Pydantic request
validation — is normalized to RFC 7807 `application/problem+json`. Try:

```bash
curl -i http://localhost:8000/api/v1/users/me   # no token → 401
```

## Project layout

See `docs/architecture.md` for the full rationale. Summary:

```
src/rag_platform/
├── main.py            # FastAPI app factory — no business logic here
├── core/               # Shared/Core: settings, logging, errors, middleware,
│                       # security primitives (hashing/JWT), pagination
├── platform/           # Cross-cutting infra: health (Phase 1); cache, queue,
│                       # storage, eventbus arrive in Phases 4, 5, 15
├── identity_access/    # Phase 2: auth, users, roles/permissions (RBAC).
│                       # In-memory persistence for now — see ADR-0005.
├── di/                 # Dependency injection container wiring
└── <other contexts>/   # document_management, indexing, retrieval,
                        # generation — added in later phases
```

Each bounded context (e.g. `identity_access/`) follows the same four-layer
structure: `api/` (thin FastAPI routers) → `application/` (use-case
services) → `domain/` (entities, ports, business rules — framework-free) ←
`infrastructure/` (port implementations). See `docs/architecture.md` for
the full layering rules and why they're enforced this way.

## Configuration

All configuration is environment-driven via `pydantic-settings`
(`src/rag_platform/core/config.py`), prefixed with `APP_`. See
`.env.example` for the full list. No secret is ever hardcoded — production
values are supplied as real environment variables, wired according to
whatever deployment platform the team ultimately chooses (the project is
intentionally platform-agnostic — see [ADR-0004](docs/adr/0004-deployment-target-platform-agnostic.md)).

# RAG Platform

Enterprise-grade Retrieval-Augmented Generation service API. See
[`docs/architecture.md`](docs/architecture.md) for the full architecture and
[`docs/adr/`](docs/adr) for the history of architectural decisions.

**Current phase: Phase 1 — repository scaffold, configuration, structured
logging, health endpoints, linting/formatting/typing, tests, and CI.** No
authentication, database, cache, storage, or RAG functionality exists yet —
those arrive in later phases (see `docs/architecture.md` §Phases).

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
```

Expected: both return `200 OK` with a JSON body, and both responses carry
`X-Request-ID` and `X-Correlation-ID` headers (generated per request, or
echoed back if you supply them yourself).

To see the RFC 7807 error format, note that no business endpoints exist yet
in Phase 1 — this is exercised by `tests/api/test_error_handling.py` against
a temporary in-test route rather than a real one.

## Project layout

See `docs/architecture.md` for the full rationale. Summary:

```
src/rag_platform/
├── main.py            # FastAPI app factory — no business logic here
├── core/               # Shared/Core: settings, logging, errors, middleware
├── platform/           # Cross-cutting infra: health (Phase 1); cache, queue,
│                       # storage, eventbus arrive in Phases 4, 5, 15
└── <bounded contexts>/ # identity_access, document_management, indexing,
                        # retrieval, generation — added starting Phase 2
```

## Configuration

All configuration is environment-driven via `pydantic-settings`
(`src/rag_platform/core/config.py`), prefixed with `APP_`. See
`.env.example` for the full list. No secret is ever hardcoded — production
values are supplied as real environment variables, wired according to
whatever deployment platform that I will ultimately choose [likely Render for testing] (the project is
intentionally platform-agnostic — see [ADR-0004](docs/adr/0004-deployment-target-platform-agnostic.md)).

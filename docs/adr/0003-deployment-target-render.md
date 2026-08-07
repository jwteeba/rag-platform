# 0003. Deployment target: Render

- **Status:** Superseded by [0004](0004-deployment-target-platform-agnostic.md)
- **Date:** 2026-08-05

> **Note (superseded):** This decision was reversed before Phase 2 began —
> see ADR-0004. Kept here, unedited, as the historical record of what was
> decided and why at the time; ADRs are not rewritten in place.

## Context

Phase 0 asked whether a specific deployment target should influence
health-check/readiness conventions early, rather than staying fully
platform-agnostic. The user chose Render.

## Decision

Target Render for deployment. Concretely, this means:

- The `Dockerfile` (Phase 1) is the deployment artifact — Render builds and
  runs it directly via its native Docker support, so no separate buildpack
  configuration is needed.
- `/health/live` and `/health/ready` (Phase 1) are structured so Render's
  health check config can point at `/health/live` for restart decisions,
  once a `render.yaml` is introduced.
- A `render.yaml` Blueprint spec is deferred to Phase 19 (Final review /
  deployment), not built now — Phase 1 scope is strictly repo scaffold,
  Docker, config, logging, health, linting, testing, and CI, per the
  project's "never generate code for future phases" rule.

## Consequences

- No PaaS-specific code exists in the application layer — Render only
  consumes the standard Dockerfile and HTTP health endpoints, so the service
  remains portable to another container platform if that ever changes.
- When Phase 19 arrives, secrets (DB URL, Redis URL, JWT signing key, OpenAI/
  Anthropic API keys, etc.) will be wired as Render environment variables /
  secret files, consistent with the "secrets must never be hardcoded" rule
  already enforced by `core/config.py`.

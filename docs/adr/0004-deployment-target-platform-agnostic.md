# 0004. Deployment target: platform-agnostic

- **Status:** Accepted
- **Date:** 2026-08-05
- **Supersedes:** [0003](0003-deployment-target-render.md)

## Context

ADR-0003 targeted Render specifically. Before Phase 2 began, the decision
was reversed: the deployment target should stay platform-agnostic rather
than being pinned to one PaaS this early.

## Decision

No specific deployment platform is assumed anywhere in the codebase.
Concretely:

- The `Dockerfile` remains the single deployment artifact — a standard
  multi-stage Docker build with no platform-specific base image, build
  step, or annotation. It runs unmodified on Render, Fly.io, ECS, Cloud
  Run, plain Kubernetes, or a bare VM with Docker installed.
- `/health/live` and `/health/ready` (Phase 1) stay generic HTTP liveness/
  readiness probes — the convention every orchestrator (Kubernetes,
  Render, ECS, Nomad, etc.) already expects, so none of them get special
  treatment.
- No platform-specific deployment manifest (`render.yaml`, a Helm chart, an
  ECS task definition, etc.) is created in this repository. Whoever deploys
  the service authors that manifest in their own infrastructure repo/tooling,
  outside this codebase's scope.
- Phase 19 (Final review / deployment) will document *how* to deploy the
  existing Dockerfile to a target of the team's choice at that time, rather
  than building deployment tooling for one platform now.

## Consequences

- No rework needed from ADR-0003: nothing Render-specific had actually been
  built into the application layer, health endpoints, or Dockerfile — the
  prior decision only existed as documentation and forward intent, so
  reversing it is a documentation change, not a code change.
- `docs/architecture.md` and `README.md` are updated to remove the Render
  reference and describe the deployment target as unresolved/agnostic by
  design.
- If a platform is chosen later, it gets its own ADR (e.g. "0005. Deployment
  target: <platform>") rather than editing this one.

# 0001. Modular monolith with bounded contexts

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

The system has five natural bounded contexts (IdentityAccess, DocumentManagement,
Indexing, Retrieval, Generation) and could be built as independently deployed
microservices or as a single deployable.

## Decision

Build as a single FastAPI deployable (modular monolith) with strict internal
boundaries enforced by directory structure and import-linting, mirroring what
a microservice split would look like.

## Consequences

Faster to build and operate initially; no distributed-transaction or
network-partition concerns between contexts yet. If a context (most likely
Indexing/Retrieval, given embedding compute cost) needs independent scaling
later, the clean boundary means it can be extracted into its own service with
comparatively low rework, since it already only talks to other contexts
through application-layer interfaces.

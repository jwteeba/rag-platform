# ADR-0009 — Celery Background Tasks

**Date:** 2026-09-02  
**Status:** Accepted  
**Phase:** 6 — Celery + background tasks

## Context

Some work must survive an HTTP request but should not delay its response.
The first case is a failed object-store delete after document metadata has
already been removed: the object is an orphan and needs retryable cleanup.

## Decision

Use **Celery** with the existing Redis deployment as both broker and result
backend. `core/celery.py` is the only factory; its broker/backend default to
`Settings.redis_url` but can be isolated through `APP_CELERY_BROKER_URL` and
`APP_CELERY_RESULT_BACKEND`. The `worker` package is the CLI entry point and
Celery auto-discovers tasks in bounded contexts.

Every task uses a common base that copies JSON-safe structlog context into
message headers and binds it in the worker. This preserves request and
correlation IDs across the process boundary.

`document_management.storage_cleanup` uses exponential backoff with jitter
and at most five retries. MinIO delete is idempotent, so retries are safe.
After the retry budget is exhausted Celery records `FAILURE` in Redis; that
terminal task state is this phase's operational dead-letter mechanism and is
visible in Flower for alerting/manual replay. Redis transport has no native
broker-side DLQ, so a separate dead-letter queue would imply a second,
durable failure-store design that is intentionally deferred.

Tests set `task_always_eager=True`, so the same task code runs synchronously
without a broker or worker. Compose runs real `celery_worker` and `flower`.

## Consequences

- API deletion removes metadata, attempts immediate object deletion, and
  enqueues cleanup only when that best-effort attempt fails.
- A broker outage never turns deletion into a client failure; it is logged
  for operations to reconcile.
- Flower is exposed on port 5555 in local Compose only; production access
  should be protected by deployment-specific authentication/network policy.

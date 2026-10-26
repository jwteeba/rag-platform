# Alerting runbook

Use Prometheus for rate/latency alerts and structured JSON logs for event alerts.
Every error event carries `level`, `error_type`, `document_id`, `user_id`, and
trace identifiers (values may be null where unavailable), so the same queries
work in CloudWatch or Datadog.

| Alert | Meaning | First diagnosis |  |
| --- | --- | --- | --- |
| Readiness degraded | A required dependency is unreachable | `/health/detailed`, dependency logs, recent deploys | 
| 5xx error rate elevated | Requests fail before completion | Filter error logs by `error_type`, open linked trace
| p95/p99 latency elevated | A dependency or downstream provider is slow | Jaeger waterfall, DB pool stats, Redis/Qdrant latency
| LLM token burn elevated | Cost or prompt growth risk | Dashboard by model/provider and `llm_usage` events
| Cache hit rate collapsed | More expensive downstream work | Cache health, TTL/config changes, Redis memory
| No Celery workers | Queued document work will stall | `/health/detailed`, Flower, worker logs


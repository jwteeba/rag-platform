# ADR 0018: Open observability defaults

## Status

Accepted.

## Context and decision

The platform needs production diagnostics without coupling application code to
one SaaS vendor. We use OpenTelemetry API/SDK and OTLP as the tracing contract,
with the OpenTelemetry Collector and Jaeger as local defaults. A deployment can
replace the collector exporter with Datadog, Honeycomb, Tempo, or a cloud-native
backend without changing application instrumentation.

Prometheus is the metrics contract and Grafana is the local visualization
default. This keeps metrics pull-based and operationally familiar while still
allowing remote-write or a managed Prometheus service. Proprietary SDKs are not
embedded in application paths; they can consume OTLP, Prometheus, and JSON logs
at the deployment edge.

FastAPI, SQLAlchemy, Redis, and HTTPX are auto-instrumented. We create explicit
spans for Celery tasks, Qdrant searches/upserts, and MinIO operations because
those clients have no suitable automatic instrumentation here. Metrics measure
aggregate volumes and latency: uploads, indexed chunks, cache outcomes,
embedding/retrieval/LLM latency, and LLM tokens. Logs retain contextual events:
request/task completion, token usage, and errors, including trace/span IDs and
portable `error_type`, `document_id`, and `user_id` dimensions.

## Consequences

Tracing can be disabled with `APP_OTEL_ENABLED`; Prometheus can be disabled
with `APP_PROMETHEUS_ENABLED`. Failures to export telemetry do not fail user
requests. Operators can use Jaeger for individual request causality and Grafana
for aggregate behavior, while JSON logs support Datadog or CloudWatch
alert rules without an application code change.

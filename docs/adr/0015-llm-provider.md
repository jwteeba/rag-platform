# ADR 0015: Swappable LLM providers

## Status
Accepted

## Decision
Generation depends on the `LLMPort`; OpenAI (`gpt-4o`) is the default and Anthropic is an explicitly configured alternative. Both adapters expose async completion and token streaming and return the same application-level result shape.

## Rationale
Keeping provider SDKs in infrastructure lets application orchestration and HTTP contracts remain independent of vendor message formats. Supporting both allows deployments to choose based on capability, availability, and commercial constraints without changing the generation workflow. Provider keys are supplied through settings and are never persisted.

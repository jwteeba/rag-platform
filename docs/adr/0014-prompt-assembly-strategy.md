# ADR-0014 — Prompt Assembly Strategy

**Status:** Accepted
**Date:** 2026-09-21
**Phase:** 10

---

## Context

Phase 10 bridges retrieval and generation: given a ranked list of chunks from
Phase 9 and a user query, it must assemble a well-structured prompt that fits
within the LLM's context window, attributes each piece of context to its source
document, and is ready to send to an LLM in Phase 11.

Three decisions needed explicit rationale: how to count tokens, how to handle
context window overflow, and how to format source attribution.

---

## Decisions

### 1. tiktoken for token counting, not character counting

Character counting (e.g. `len(text) // 4`) is a common approximation but
produces errors of 10–30% depending on content — code, URLs, and non-ASCII
text all skew the ratio. Sending a prompt that's 10% over the context window
causes a hard API error from the LLM provider; sending one that's 30% under
wastes context budget that could hold more relevant chunks.

`tiktoken` is OpenAI's own tokenizer library. It produces exact token counts
for GPT-3.5, GPT-4, and GPT-4o models. For models tiktoken doesn't recognise
by name, we fall back to `cl100k_base` — the encoding shared by GPT-4 and
GPT-4o — which is correct for all current OpenAI chat models.

`TokenCounterPort` is a protocol so a future phase can swap in a HuggingFace
tokenizer for non-OpenAI models without changing `PromptAssemblyService`.

### 2. Greedy chunk fitting, drop lowest-scoring chunks first

Chunks arrive from `RetrievalService` already ranked by cosine similarity
(highest score first). `PromptAssemblyService` iterates them in order and
greedily adds each chunk if it fits within the remaining token budget. When a
chunk doesn't fit it is skipped entirely — we never truncate a chunk
mid-sentence, because a partial chunk is more likely to mislead the LLM than
to help it.

The highest-scoring chunks are always included first; the lowest-scoring ones
are the first to be dropped when the budget is tight. This is the correct
priority ordering for RAG: relevance > completeness.

Token budget: `max_context_tokens - count(system_prompt) - count(query)`.
`APP_MAX_CONTEXT_TOKENS` defaults to 6000, leaving headroom for the LLM's
response within an 8192-token model limit. GPT-4o supports 128k, so this is
conservative and adjustable per deployment.

### 3. Inline source attribution

Each chunk is prefixed with `[Source: {filename}, chunk {chunk_index}]` before
being inserted into the context block. The LLM sees attribution inline with the
content it's reading, making it straightforward to cite sources in its response
without a separate post-processing step.

The alternative — passing source metadata separately and asking the LLM to
correlate it — requires more complex prompt engineering and produces less
reliable citations.

### 4. Prompt templates in Postgres, seeded at startup

Templates (`system_prompt` + `user_template`) are stored in the
`prompt_templates` table rather than hardcoded. This allows admins to update
prompts without a code deployment and supports A/B testing in a future phase.

Two defaults are seeded at startup (idempotent): `general-qa` and
`summarization`. `APP_DEFAULT_PROMPT_TEMPLATE_NAME` controls which is used
when no `template_id` is supplied to the assembly endpoint.

Template variables are `{context}` and `{query}`, rendered with Python's
`str.format()`. A missing variable raises `TemplateRenderError` (422) rather
than silently producing a malformed prompt.

---

## Consequences

- `tiktoken` adds a small dependency and a one-time encoding load per process.
- The greedy fitting strategy means a single large high-scoring chunk can crowd
  out several smaller lower-scoring ones. This is acceptable — one highly
  relevant chunk is more useful than several marginally relevant ones.
- Templates are admin-only CRUD. Members cannot modify them, preventing prompt
  injection via the template system.

"""Application-owned Prometheus metrics.

Metric objects live in one module so labels and names remain stable across
routers, workers, and adapters.  Instrumentation failures must never affect
the RAG request path, so callers use these objects only for best-effort
observation.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

GUARDRAIL_REJECTIONS = Counter(
    "rag_guardrail_rejections_total",
    "Requests rejected by an input/output guardrail.",
    ["rule", "path"],
)
DOCUMENTS_UPLOADED = Counter(
    "rag_documents_uploaded_total", "Documents accepted for processing.", ["content_type"]
)
CHUNKS_INDEXED = Counter("rag_chunks_indexed_total", "Chunks successfully indexed in Qdrant.")
LLM_TOKENS_USED = Counter(
    "rag_llm_tokens_used_total", "Tokens used by LLM requests.", ["model", "provider"]
)
CACHE_HITS = Counter("rag_cache_hits_total", "Cache hits.", ["cache_layer"])
CACHE_MISSES = Counter("rag_cache_misses_total", "Cache misses.", ["cache_layer"])
RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_latency_seconds", "End-to-end retrieval latency in seconds."
)
LLM_LATENCY = Histogram("rag_llm_latency_seconds", "LLM completion latency in seconds.", ["model"])
EMBEDDING_LATENCY = Histogram("rag_embedding_latency_seconds", "Embedding latency in seconds.")

# User / auth metrics
USER_REGISTRATIONS = Counter("rag_user_registrations_total", "Successful user registrations.")
USER_LOGINS = Counter("rag_user_logins_total", "Successful user logins.")
USER_LOGIN_FAILURES = Counter(
    "rag_user_login_failures_total",
    "Failed login attempts.",
    ["reason"],  # invalid_credentials | inactive_account
)
TOKEN_REFRESHES = Counter("rag_token_refreshes_total", "Successful token refreshes.")
TOKEN_REUSE_ATTEMPTS = Counter(
    "rag_token_reuse_attempts_total",
    "Refresh token reuse attempts (possible session hijack).",
)
USER_LOGOUTS = Counter("rag_user_logouts_total", "Explicit user logouts.")
USER_GUARDRAIL_REJECTIONS = Counter(
    "rag_user_guardrail_rejections_total",
    "Guardrail rejections attributed to a specific user.",
    ["rule", "user_id"],
)

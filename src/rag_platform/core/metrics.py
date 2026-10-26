"""Application-owned Prometheus metrics.

Metric objects live in one module so labels and names remain stable across
routers, workers, and adapters.  Instrumentation failures must never affect
the RAG request path, so callers use these objects only for best-effort
observation.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

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

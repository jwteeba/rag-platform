# ADR 0017: Multi-layer RAG caching

## Status
Accepted

## Decision

Use three independent Redis cache-aside layers:

1. **Embeddings:** exact SHA-256 text digest, namespaced by embedding provider/model. The 24-hour default TTL reflects that embeddings are immutable for a fixed model and input. This layer is shared across documents and queries.
2. **Vector search:** exact query-vector digest with owner, result limit, score threshold, and sorted document filter in the key. The 10-minute default TTL limits stale search results. Deleting a document best-effort deletes all retrieval entries for that owner; indexing relies on TTL, so fresh chunks may be absent from cached results briefly.
3. **LLM responses:** compare query embeddings by cosine similarity, with owner and generation namespace isolation. The default threshold is 0.97 and TTL is five minutes. Entries also include model/provider, generation settings, prompt template name, retrieval limit, and conversation history digest in their namespace. Responses are reused only within the same owner's namespace.

## Tradeoffs

Exact embedding and retrieval keys avoid false semantic matches. The LLM cache can return an answer for a meaningfully different question whose embedding is still above the threshold. A high default reduces, but cannot eliminate, that risk. The namespace prevents cross-owner leakage and separates model/config/history variants; retrieved-document changes can still leave a response stale until the short TTL expires. LLM entries are TTL-only and are not invalidated on indexing or deletion.

All caches fail open: Redis errors fall through to the original embedding, vector-search, or LLM path. Hit/miss counters and structured latency logs are recorded for each lookup. Cache keys have layer prefixes so the admin statistics endpoint can report per-layer key counts, hit rates, and Redis memory usage.

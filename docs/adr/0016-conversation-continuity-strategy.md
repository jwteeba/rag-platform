# ADR 0016: Conversation continuity and token budget

## Status
Accepted

## Decision
For each turn, generation loads at most `max_conversation_history_messages` newest prior messages in chronological order, then adds the assembled system prompt, retrieved context, and current query. The current turn is saved only after provider completion. Streaming turns are saved after the stream finishes.

## Budget
The service rejects a turn with `ContextWindowExceededError` when history plus prompt/context/query plus the configured completion reserve (`llm_max_tokens`) exceeds `max_context_tokens`. Operators should size this limit for their selected model. Retrieval assembly independently drops chunks that do not fit its context allowance.

"""tiktoken-based token counter implementing TokenCounterPort."""

from __future__ import annotations

import tiktoken


class TiktokenCounter:
    """Counts tokens using tiktoken for accurate pre-flight LLM budget checks.

    Uses the encoding for the configured model. Falls back to `cl100k_base`
    (GPT-4/GPT-3.5 encoding) for any model tiktoken doesn't recognise by
    name — this is the correct fallback for gpt-4o and most modern OpenAI
    models. See ADR-0014.
    """

    def __init__(self, model: str) -> None:
        try:
            self._enc = tiktoken.encoding_for_model(model)
        except KeyError:
            self._enc = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

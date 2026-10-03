"""Anthropic implementation of the generation LLM port."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from rag_platform.generation.domain.exceptions import LLMUnavailableError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class AnthropicLLMAdapter:
    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise LLMUnavailableError(
                "APP_ANTHROPIC_API_KEY must be configured to generate answers."
            )
        try:
            AsyncAnthropic = import_module("anthropic").AsyncAnthropic
            self._client = AsyncAnthropic(api_key=api_key)
        except ImportError as exc:
            raise LLMUnavailableError(
                "Install the anthropic package to use this provider."
            ) from exc

    @staticmethod
    def _request(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        rest = [
            {"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"
        ]
        return system, rest

    async def complete(
        self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int
    ) -> tuple[str, int, int]:
        system, conversation = self._request(messages)
        try:
            result = await self._client.messages.create(
                model=model,
                system=system,
                messages=conversation,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = "".join(
                block.text for block in result.content if getattr(block, "type", None) == "text"
            )
            return text, result.usage.input_tokens, result.usage.output_tokens
        except Exception as exc:
            raise LLMUnavailableError() from exc

    async def stream(
        self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        system, conversation = self._request(messages)
        try:
            async with self._client.messages.stream(
                model=model,
                system=system,
                messages=conversation,
                temperature=temperature,
                max_tokens=max_tokens,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            raise LLMUnavailableError() from exc

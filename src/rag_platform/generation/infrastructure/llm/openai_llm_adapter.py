"""OpenAI implementation of the generation LLM port."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from openai import AsyncOpenAI

from rag_platform.generation.domain.exceptions import LLMUnavailableError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from openai.types.chat import ChatCompletionMessageParam


class OpenAILLMAdapter:
    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise LLMUnavailableError("APP_OPENAI_API_KEY must be configured to generate answers.")
        self._client = AsyncOpenAI(api_key=api_key)

    async def complete(
        self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int
    ) -> tuple[str, int, int]:
        try:
            result = await self._client.chat.completions.create(
                model=model,
                messages=cast("list[ChatCompletionMessageParam]", messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            usage = result.usage
            return (
                result.choices[0].message.content or "",
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            )
        except Exception as exc:
            raise LLMUnavailableError() from exc

    async def stream(
        self, messages: list[dict[str, str]], *, model: str, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=cast("list[ChatCompletionMessageParam]", messages),
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                text = chunk.choices[0].delta.content
                if text:
                    yield text
        except Exception as exc:
            raise LLMUnavailableError() from exc

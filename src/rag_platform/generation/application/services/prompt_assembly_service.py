"""PromptAssemblyService: fit chunks into context window, render template."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_platform.generation.domain.entities import AssembledPrompt
from rag_platform.generation.domain.exceptions import TemplateNotFoundError, TemplateRenderError

if TYPE_CHECKING:
    import uuid

    from rag_platform.generation.domain.ports import PromptTemplateRepositoryPort, TokenCounterPort
    from rag_platform.retrieval.domain.entities import SearchResult


class PromptAssemblyService:
    def __init__(
        self,
        template_repo: PromptTemplateRepositoryPort,
        token_counter: TokenCounterPort,
        max_context_tokens: int,
        default_template_name: str,
    ) -> None:
        self._template_repo = template_repo
        self._token_counter = token_counter
        self._max_context_tokens = max_context_tokens
        self._default_template_name = default_template_name

    async def assemble(
        self,
        query: str,
        chunks: list[SearchResult],
        *,
        template_id: uuid.UUID | None = None,
    ) -> AssembledPrompt:
        """Fit as many top-ranked chunks as possible within the context window.

        Chunks are already ranked by score (highest first) from RetrievalService.
        We greedily add chunks until the next one would exceed the budget, then
        stop — lowest-scoring chunks are dropped first. We never truncate a chunk
        mid-sentence; it's either included whole or dropped entirely.
        """
        if template_id is not None:
            template = await self._template_repo.get_by_id(template_id)
            if template is None:
                raise TemplateNotFoundError()
        else:
            template = await self._template_repo.get_by_name(self._default_template_name)
            if template is None:
                raise TemplateNotFoundError(
                    f"Default template '{self._default_template_name}' not found."
                )

        # Reserve tokens for the system prompt and the query itself.
        reserved = self._token_counter.count(template.system_prompt) + self._token_counter.count(
            query
        )
        budget = self._max_context_tokens - reserved

        fitted: list[tuple[str, int, str]] = []
        for chunk in chunks:
            chunk_tokens = self._token_counter.count(chunk.content)
            if chunk_tokens <= budget:
                fitted.append((chunk.filename, chunk.chunk_index, chunk.content))
                budget -= chunk_tokens

        # Render the user template — expects {context} and {query} variables.
        context_text = "\n\n".join(
            f"[Source: {fn}, chunk {idx}]\n{content}" for fn, idx, content in fitted
        )
        try:
            rendered_user = template.user_template.format(context=context_text, query=query)
        except KeyError as exc:
            raise TemplateRenderError(
                f"Template '{template.name}' is missing variable: {exc}"
            ) from exc

        total_tokens = self._token_counter.count(
            template.system_prompt
        ) + self._token_counter.count(rendered_user)

        return AssembledPrompt(
            system_prompt=template.system_prompt,
            context_chunks=fitted,
            user_query=query,
            token_count=total_tokens,
            rendered_user_prompt=rendered_user,
        )

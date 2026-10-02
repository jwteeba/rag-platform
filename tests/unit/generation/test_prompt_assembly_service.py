"""Unit tests for PromptAssemblyService."""

from __future__ import annotations

import uuid

import pytest

from rag_platform.generation.application.services.prompt_assembly_service import (
    PromptAssemblyService,
)
from rag_platform.generation.domain.entities import PromptTemplate
from rag_platform.generation.domain.exceptions import TemplateNotFoundError, TemplateRenderError
from rag_platform.retrieval.domain.entities import SearchResult


def _make_template(
    name: str = "general-qa",
    system_prompt: str = "You are a helpful assistant.",
    user_template: str = "Context:\n{context}\n\nQuestion: {query}\n\nAnswer:",
) -> PromptTemplate:
    return PromptTemplate.create(
        name=name,
        system_prompt=system_prompt,
        user_template=user_template,
        model_target="gpt-4o",
    )


def _make_chunk(content: str, score: float = 0.9, chunk_index: int = 0) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="doc.pdf",
        content=content,
        score=score,
        chunk_index=chunk_index,
    )


class FakeTokenCounter:
    """Counts words as tokens for deterministic tests."""

    def count(self, text: str) -> int:
        return len(text.split())


class FakeTemplateRepo:
    def __init__(self, templates: list[PromptTemplate] | None = None) -> None:
        self._by_id = {t.id: t for t in (templates or [])}
        self._by_name = {t.name: t for t in (templates or [])}

    async def add(self, template: PromptTemplate) -> None:
        self._by_id[template.id] = template
        self._by_name[template.name] = template

    async def get_by_id(self, template_id: uuid.UUID) -> PromptTemplate | None:
        return self._by_id.get(template_id)

    async def get_by_name(self, name: str) -> PromptTemplate | None:
        return self._by_name.get(name)

    async def list_all(self) -> list[PromptTemplate]:
        return list(self._by_id.values())

    async def update(self, template: PromptTemplate) -> None:
        self._by_id[template.id] = template
        self._by_name[template.name] = template

    async def delete(self, template_id: uuid.UUID) -> None:
        t = self._by_id.pop(template_id, None)
        if t:
            self._by_name.pop(t.name, None)


def _service(
    templates: list[PromptTemplate] | None = None,
    max_context_tokens: int = 1000,
    default_name: str = "general-qa",
) -> PromptAssemblyService:
    return PromptAssemblyService(
        template_repo=FakeTemplateRepo(templates),
        token_counter=FakeTokenCounter(),
        max_context_tokens=max_context_tokens,
        default_template_name=default_name,
    )


@pytest.mark.asyncio
async def test_assembles_prompt_with_default_template() -> None:
    template = _make_template()
    svc = _service(templates=[template])
    chunk = _make_chunk("Python is a programming language.")

    result = await svc.assemble("What is Python?", [chunk])

    assert result.system_prompt == template.system_prompt
    assert result.user_query == "What is Python?"
    assert len(result.context_chunks) == 1
    assert result.context_chunks[0][2] == "Python is a programming language."


@pytest.mark.asyncio
async def test_uses_explicit_template_id() -> None:
    default = _make_template(name="general-qa")
    other = _make_template(name="summarization", system_prompt="Summarize this.")
    svc = _service(templates=[default, other])
    chunk = _make_chunk("Some content.")

    result = await svc.assemble("Summarize", [chunk], template_id=other.id)

    assert result.system_prompt == "Summarize this."


@pytest.mark.asyncio
async def test_raises_template_not_found_for_unknown_id() -> None:
    svc = _service(templates=[])
    with pytest.raises(TemplateNotFoundError):
        await svc.assemble("query", [], template_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_raises_template_not_found_when_default_missing() -> None:
    svc = _service(templates=[])
    with pytest.raises(TemplateNotFoundError):
        await svc.assemble("query", [])


@pytest.mark.asyncio
async def test_context_window_fitting_drops_lowest_scoring_chunks() -> None:
    template = _make_template()
    # FakeTokenCounter counts words. system_prompt="You are a helpful assistant." = 5 words
    # query="q" = 1 word → reserved = 6. budget = 20 - 6 = 14 words.
    # chunk1: "one two three four five" = 5 words → fits, budget=9
    # chunk2: "six seven eight nine ten" = 5 words → fits, budget=4
    # chunk3: "eleven twelve thirteen fourteen fifteen" = 5 words → doesn't fit (5 > 4)
    svc = _service(templates=[template], max_context_tokens=20)
    chunks = [
        _make_chunk("one two three four five", score=0.9, chunk_index=0),
        _make_chunk("six seven eight nine ten", score=0.8, chunk_index=1),
        _make_chunk("eleven twelve thirteen fourteen fifteen", score=0.7, chunk_index=2),
    ]

    result = await svc.assemble("q", chunks)

    assert len(result.context_chunks) == 2
    assert result.context_chunks[0][2] == "one two three four five"
    assert result.context_chunks[1][2] == "six seven eight nine ten"


@pytest.mark.asyncio
async def test_token_count_is_accurate() -> None:
    template = _make_template(
        system_prompt="System.",
        user_template="Context:\n{context}\n\nQuestion: {query}\n\nAnswer:",
    )
    svc = _service(templates=[template])
    chunk = _make_chunk("hello world")

    result = await svc.assemble("test query", [chunk])

    assert result.token_count > 0


@pytest.mark.asyncio
async def test_rendered_context_includes_source_attribution() -> None:
    template = _make_template()
    svc = _service(templates=[template])
    chunk = _make_chunk("Important fact.", chunk_index=3)
    chunk.filename = "report.pdf"

    result = await svc.assemble("query", [chunk])

    assert "report.pdf" in result.rendered_context
    assert "chunk 3" in result.rendered_context


@pytest.mark.asyncio
async def test_raises_template_render_error_for_bad_template() -> None:
    template = _make_template(user_template="Context: {context} Query: {query} Extra: {missing}")
    svc = _service(templates=[template])

    with pytest.raises(TemplateRenderError):
        await svc.assemble("query", [_make_chunk("content")])


@pytest.mark.asyncio
async def test_empty_chunks_assembles_with_empty_context() -> None:
    template = _make_template()
    svc = _service(templates=[template])

    result = await svc.assemble("What is Python?", [])

    assert result.context_chunks == []
    assert result.rendered_context == ""

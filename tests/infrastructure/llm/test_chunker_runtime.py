from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.llm.chunker import ChunkerService


def test_large_structured_text_is_split_into_multiple_chunks() -> None:
    text = "\n\n".join(
        f"## Section {index}\n"
        f"This section contains enough operational knowledge for chunk {index}. "
        f"It should remain readable and independently indexable."
        for index in range(30)
    )

    chunks = ChunkerService(chunk_size=240, overlap=40).chunk_text(text)

    assert len(chunks) > 5
    assert all(isinstance(chunk, str) and chunk.strip() for chunk in chunks)


@pytest.mark.asyncio
async def test_markdown_file_is_supported_as_source_blocks_only() -> None:
    chunker = ChunkerService(chunk_size=500, overlap=50)

    chunks = await chunker.process_file(
        b"# Test\n\nMarkdown knowledge text about uploading documents.",
        "test.md",
    )

    assert chunks
    assert all(isinstance(chunk, str) for chunk in chunks)
    joined = "\n".join(str(chunk) for chunk in chunks)
    assert "Test" in joined
    assert "Markdown knowledge text" in joined
    assert "plain_enriched" not in joined
    assert "embedding_text" not in joined


@pytest.mark.asyncio
async def test_json_intent_knowledge_file_is_supported() -> None:
    chunker = ChunkerService(chunk_size=500, overlap=50)

    chunks = await chunker.process_file(
        (
            b'{"intents":{"connect_manager":{'
            b'"answer":"Manager can be connected from project settings.",'
            b'"synonyms":["operator","human support"],'
            b'"keywords":["manager","handoff"]'
            b"}}}"
        ),
        "intents.json",
    )

    joined = "\n".join(str(chunk) for chunk in chunks)
    assert "connect_manager" in joined
    assert "answer: Manager can be connected from project settings." in joined
    assert "synonyms: operator, human support" in joined


@pytest.mark.asyncio
async def test_markdown_file_returns_plain_section_strings() -> None:
    chunker = ChunkerService(chunk_size=280, overlap=40)

    chunks = await chunker.process_file(
        (
            "# Knowledge base\n\n"
            "Introductory product text.\n\n"
            "## Refunds\n\n"
            "Refund requests are reviewed by a manager.\n\n"
            "## Delivery\n\n"
            "Delivery questions are answered from the client project knowledge base."
        ).encode("utf-8"),
        "kb.md",
    )

    assert chunks
    assert all(isinstance(chunk, str) for chunk in chunks)
    joined = "\n".join(str(chunk) for chunk in chunks)
    assert "Refunds" in joined
    assert "Delivery" in joined


def test_chunker_source_does_not_build_semantic_metadata() -> None:
    text = Path("src/infrastructure/llm/chunker.py").read_text(encoding="utf-8")

    assert "plain_enriched" not in text
    assert "chunk_markdown_enriched" not in text
    assert "_markdown_embedding_text" not in text
    assert "json_value_from_unknown" not in text

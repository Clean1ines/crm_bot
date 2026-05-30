from __future__ import annotations

from src.application.services.knowledge_answer_compiler_batching import (
    KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET,
    build_technical_chunk_batches_for_answer_compiler,
)


def test_plain_chunk_over_char_budget_splits_by_paragraphs() -> None:
    first = "A" * 420
    second = "B" * 420

    batches = build_technical_chunk_batches_for_answer_compiler(
        [
            {
                "content": f"{first}\n\n{second}",
                "index": 7,
                "page": 3,
                "custom": "preserved",
            }
        ]
    )

    assert len(batches) == 2
    assert [len(batch) for batch in batches] == [1, 1]

    first_chunk = batches[0][0]
    second_chunk = batches[1][0]

    assert first_chunk["content"] == first
    assert second_chunk["content"] == second
    assert first_chunk["technical_part_index"] == 1
    assert second_chunk["technical_part_index"] == 2
    assert first_chunk["technical_part_count"] == 2
    assert second_chunk["technical_part_count"] == 2
    assert first_chunk["technical_source_char_budget"] == (
        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
    )


def test_markdown_semantic_chunk_does_not_split_even_over_char_budget() -> None:
    content = ("# Heading\n\n" + "semantic text " * 80).strip()

    batches = build_technical_chunk_batches_for_answer_compiler(
        [
            {
                "content": content,
                "section_title": "FAQ section",
                "children": [{"title": "child"}],
            }
        ]
    )

    assert len(batches) == 1
    chunk = batches[0][0]
    assert chunk["content"] == content
    assert chunk["technical_part_index"] == 1
    assert chunk["technical_part_count"] == 1


def test_empty_chunks_are_skipped() -> None:
    batches = build_technical_chunk_batches_for_answer_compiler(
        [
            {"content": ""},
            {"content": "   \n\t "},
            {"title": "no content"},
        ]
    )

    assert batches == ()


def test_technical_metadata_is_added_without_dropping_source_metadata() -> None:
    batches = build_technical_chunk_batches_for_answer_compiler(
        [
            {
                "id": "chunk-1",
                "index": 9,
                "content": "Short source text",
                "page": 4,
                "source_excerpt": "Short source text",
                "tags": ["faq", "source"],
                "metadata": {"origin": "upload"},
            }
        ]
    )

    assert len(batches) == 1
    chunk = batches[0][0]

    assert chunk["id"] == "chunk-1"
    assert chunk["index"] == 9
    assert chunk["page"] == 4
    assert chunk["source_excerpt"] == "Short source text"
    assert chunk["tags"] == ["faq", "source"]
    assert chunk["metadata"] == {"origin": "upload"}
    assert chunk["technical_part_index"] == 1
    assert chunk["technical_part_count"] == 1
    assert chunk["technical_source_char_budget"] == (
        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
    )

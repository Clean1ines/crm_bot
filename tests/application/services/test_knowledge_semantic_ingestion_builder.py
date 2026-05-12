from __future__ import annotations

from src.application.services.knowledge_ingestion_service import (
    _document_from_json_chunks,
)


def test_document_from_plain_markdown_chunks_uses_semantic_builder() -> None:
    document = _document_from_json_chunks(
        file_name="kb.md",
        chunks=[
            {
                "content": (
                    "# Manager handoff\n\n"
                    "Assistant transfers complex payment questions to a human manager."
                )
            }
        ],
    )

    assert len(document.blocks) == 1
    assert len(document.chunks) == 1
    chunk = document.chunks[0]
    assert chunk.title == "Manager handoff"
    assert chunk.source_excerpt == (
        "Assistant transfers complex payment questions to a human manager."
    )
    assert chunk.section_path.title == "kb.md / Manager handoff"


def test_document_from_structured_chunks_preserves_llm_metadata() -> None:
    document = _document_from_json_chunks(
        file_name="kb.md",
        chunks=[
            {
                "content": "Assistant transfers complex questions to a human manager.",
                "entry_kind": "faq_answer",
                "title": "Manager handoff",
                "source_excerpt": "Assistant transfers complex questions.",
                "questions": ["Can I talk to a manager?"],
                "synonyms": ["operator"],
                "tags": ["handoff"],
                "embedding_text": "Manager handoff operator human support",
            }
        ],
    )

    assert document.blocks == ()
    assert len(document.chunks) == 1
    chunk = document.chunks[0]
    assert chunk.title == "Manager handoff"
    assert chunk.source_excerpt == "Assistant transfers complex questions."
    assert chunk.questions == ("Can I talk to a manager?",)
    assert chunk.embedding_text == "Manager handoff operator human support"

from __future__ import annotations

from src.domain.project_plane.knowledge_document_structure import KnowledgeDocumentBlock
from src.domain.project_plane.knowledge_semantic_builder import (
    build_knowledge_chunk_drafts,
)


def test_semantic_builder_derives_title_excerpt_tags_from_markdown_block() -> None:
    block = KnowledgeDocumentBlock(
        content=(
            "# Product overview\n\n"
            "CRM routes client questions to knowledge search and manager handoff."
        )
    )

    drafts = build_knowledge_chunk_drafts(
        document_title="docs.md",
        blocks=(block,),
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.title == "Product overview"
    assert draft.source_excerpt == (
        "CRM routes client questions to knowledge search and manager handoff."
    )
    assert draft.section_path.title == "docs.md / Product overview"
    assert "overview" in draft.tags
    assert draft.embedding_text == ""
    assert draft.metadata["semantic_builder"] == "deterministic_v1"


def test_semantic_builder_keeps_plain_block_without_fake_markdown_title() -> None:
    block = KnowledgeDocumentBlock(
        content="Client messages are split into separate questions before RAG lookup."
    )

    drafts = build_knowledge_chunk_drafts(
        document_title="plain.txt",
        blocks=(block,),
    )

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.title == ""
    assert draft.source_excerpt == (
        "Client messages are split into separate questions before RAG lookup."
    )
    assert draft.section_path.title == "plain.txt"

from __future__ import annotations

from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
)
from src.domain.project_plane.knowledge_document_structure import KnowledgeDocumentBlock
from src.domain.project_plane.knowledge_semantic_builder import (
    build_knowledge_chunk_drafts,
    canonicalize_knowledge_chunk_drafts,
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


def test_semantic_builder_merges_duplicate_meanings_without_doc_specific_sections() -> (
    None
):
    blocks = (
        KnowledgeDocumentBlock(
            content=(
                "## Pricing\n\n"
                "The service cost depends on configuration, integrations, "
                "team size and support requirements. A manager should calculate "
                "the final price."
            )
        ),
        KnowledgeDocumentBlock(
            content=(
                "### How much does it cost?\n\n"
                "The service cost depends on configuration, integrations, "
                "team size and support requirements. A manager should calculate "
                "the final price."
            )
        ),
    )

    drafts = build_knowledge_chunk_drafts(
        document_title="knowledge.md",
        blocks=blocks,
    )

    assert len(drafts) == 1
    assert drafts[0].title == "Pricing"
    assert "How much does it cost?" in drafts[0].questions
    assert "configuration" in drafts[0].content


def test_question_heading_is_query_surface_without_losing_answer_body() -> None:
    blocks = (
        KnowledgeDocumentBlock(
            content=(
                "## Pricing\nThe service cost depends on configuration and support."
            )
        ),
        KnowledgeDocumentBlock(
            content=(
                "### How much does it cost?\n"
                "The service cost depends on configuration and support.\n"
                "Integrations change the final estimate."
            )
        ),
    )

    drafts = build_knowledge_chunk_drafts(
        document_title="customer_knowledge.md",
        blocks=blocks,
    )

    assert len(drafts) == 1
    assert drafts[0].title == "Pricing"
    assert "How much does it cost?" in drafts[0].questions
    assert "The service cost depends on configuration and support." in drafts[0].content
    assert "Integrations change the final estimate." in drafts[0].content
    assert (
        drafts[0].content.count(
            "The service cost depends on configuration and support."
        )
        == 1
    )


def test_untitled_plain_chunks_are_not_merged_by_term_overlap_only() -> None:
    drafts = canonicalize_knowledge_chunk_drafts(
        document_title="plain.txt",
        drafts=(
            KnowledgeChunkDraft(
                content=(
                    "First useful knowledge paragraph with enough content "
                    "for plain upload and retrieval routing."
                )
            ),
            KnowledgeChunkDraft(
                content=(
                    "Second useful knowledge paragraph with enough content "
                    "for plain upload and retrieval routing."
                )
            ),
        ),
    )

    assert len(drafts) == 2
    assert all(draft.title == "" for draft in drafts)


def test_single_structured_chunk_preserves_explicit_source_excerpt() -> None:
    drafts = canonicalize_knowledge_chunk_drafts(
        document_title="kb.md",
        drafts=(
            KnowledgeChunkDraft(
                content="Assistant transfers complex questions to a human manager.",
                title="Manager handoff",
                source_excerpt="Assistant transfers complex questions.",
                questions=("Can I talk to a manager?",),
            ),
        ),
    )

    assert len(drafts) == 1
    assert drafts[0].source_excerpt == "Assistant transfers complex questions."
    assert (
        drafts[0].content == "Assistant transfers complex questions to a human manager."
    )


def test_same_title_different_content_is_not_canonicalized_as_duplicate() -> None:
    drafts = build_knowledge_chunk_drafts(
        document_title="kb.md",
        blocks=(
            KnowledgeDocumentBlock(
                content=(
                    "## FAQ\n\n"
                    "Клиент может загрузить документы через веб-панель проекта. "
                    "После загрузки документ уходит в очередь обработки базы знаний."
                )
            ),
            KnowledgeDocumentBlock(
                content=(
                    "## FAQ\n\n"
                    "Менеджер получает уведомление только после эскалации диалога. "
                    "Обычные клиентские сообщения не требуют ручного ответа."
                )
            ),
        ),
    )

    assert len(drafts) == 2
    assert any("загрузить документы" in draft.content for draft in drafts)
    assert any(
        "уведомление только после эскалации" in draft.content for draft in drafts
    )


def test_answerable_and_internal_eval_chunks_are_not_canonicalized_together() -> None:
    drafts = canonicalize_knowledge_chunk_drafts(
        document_title="kb.md",
        drafts=(
            KnowledgeChunkDraft(
                content=(
                    "Менеджер подключается к диалогу после эскалации. "
                    "Клиент получает ответ от человека в том же канале."
                ),
                role=KnowledgeChunkRole.ANSWER_KNOWLEDGE,
                title="Эскалация к менеджеру",
            ),
            KnowledgeChunkDraft(
                content=(
                    "Менеджер подключается к диалогу после эскалации. "
                    "Клиент получает ответ от человека в том же канале."
                ),
                role=KnowledgeChunkRole.INTERNAL_EVAL_TEST,
                title="Эскалация к менеджеру",
            ),
        ),
    )

    assert len(drafts) == 2
    assert {draft.role for draft in drafts} == {
        KnowledgeChunkRole.ANSWER_KNOWLEDGE,
        KnowledgeChunkRole.INTERNAL_EVAL_TEST,
    }

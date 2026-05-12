from __future__ import annotations

from src.application.services.knowledge_normalization_service import (
    KnowledgeNormalizationService,
)
from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
    KnowledgeSectionPath,
)
from src.domain.project_plane.knowledge_document_structure import (
    KnowledgeDocumentSource,
    ParsedKnowledgeDocument,
)

PROJECT_ID = "project_1"
DOCUMENT_ID = "document_1"


def _document(*chunks: KnowledgeChunkDraft) -> ParsedKnowledgeDocument:
    return ParsedKnowledgeDocument(
        source=KnowledgeDocumentSource(
            filename="knowledge.md", content_type="text/markdown"
        ),
        chunks=chunks,
    )


def test_normalization_classifies_and_builds_embedding_text() -> None:
    service = KnowledgeNormalizationService()
    document = _document(
        KnowledgeChunkDraft(
            content="Frequently asked questions\n\nQ: Can I upload documents?\nA: Yes, supported files can be uploaded.",
            title="FAQ",
            section_path=KnowledgeSectionPath(("FAQ",)),
        )
    )

    result = service.normalize_document(
        document,
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert result.total_chunks == 1
    chunk = result.chunks[0]
    assert chunk.role == KnowledgeChunkRole.FAQ
    assert "FAQ" in chunk.embedding_text
    assert "Can I upload documents" in chunk.embedding_text


def test_normalization_filters_non_indexable_separator_chunks() -> None:
    service = KnowledgeNormalizationService()
    document = _document(
        KnowledgeChunkDraft(
            content="---",
            title="Separator",
            section_path=KnowledgeSectionPath(("Separator",)),
        ),
        KnowledgeChunkDraft(
            content="This is a real knowledge paragraph with enough useful content to index.",
            title="Useful section",
            section_path=KnowledgeSectionPath(("Useful section",)),
        ),
    )

    result = service.normalize_document(
        document,
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert result.total_chunks == 1
    assert result.chunks[0].title == "Useful section"


def test_answerable_chunks_excludes_internal_eval_material() -> None:
    service = KnowledgeNormalizationService()
    document = _document(
        KnowledgeChunkDraft(
            content="Expected answer: user should receive this only in an evaluation dataset.",
            title="Evaluation tests",
            section_path=KnowledgeSectionPath(("Evaluation tests",)),
        ),
        KnowledgeChunkDraft(
            content="The service lets customers upload knowledge documents and answer from them.",
            title="Product capability",
            section_path=KnowledgeSectionPath(("Product capability",)),
        ),
    )

    result = service.normalize_document(
        document,
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert result.total_chunks == 2
    assert len(result.answerable_chunks) == 1
    assert result.answerable_chunks[0].role == KnowledgeChunkRole.ANSWER_KNOWLEDGE


def test_normalization_service_source_does_not_use_legacy_chunk_contract() -> None:
    source = "src/application/services/knowledge_normalization_service.py"
    text = open(source, encoding="utf-8").read()

    forbidden = (
        "JsonObject",
        "entry_kind",
        "plain_enriched",
        "add_knowledge_batch",
        "add_structured_knowledge_batch",
        "list[str |",
        "to_legacy",
        "from_legacy",
    )

    for marker in forbidden:
        assert marker not in text

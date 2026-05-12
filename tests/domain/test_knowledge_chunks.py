from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from src.domain.project_plane.knowledge_chunks import (
    ANSWERABLE_KNOWLEDGE_ROLES,
    NON_ANSWER_KNOWLEDGE_ROLES,
    KnowledgeChunk,
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
    KnowledgeSectionPath,
)


def test_chunk_draft_normalizes_text_fields_and_dedupes_sequences() -> None:
    draft = KnowledgeChunkDraft(
        content="  Some   content  ",
        title="  Main   title ",
        source_excerpt="  Short   excerpt ",
        questions=("  Q1? ", "Q1?", " Q2? "),
        synonyms=(" alias ", "alias"),
        tags=(" tag ", "tag"),
    )

    assert draft.content == "Some content"
    assert draft.title == "Main title"
    assert draft.source_excerpt == "Short excerpt"
    assert draft.questions == ("Q1?", "Q2?")
    assert draft.synonyms == ("alias",)
    assert draft.tags == ("tag",)


def test_chunk_draft_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="content must not be empty"):
        KnowledgeChunkDraft(content="   ")


def test_section_path_builds_hierarchical_title() -> None:
    section = KnowledgeSectionPath(
        document_title=" Product docs ",
        headings=(" Setup ", " Step one "),
    )

    assert section.title == "Product docs / Setup / Step one"
    assert section.leaf == "Step one"


def test_answerable_roles_are_explicit() -> None:
    assert KnowledgeChunkRole.ANSWER_KNOWLEDGE in ANSWERABLE_KNOWLEDGE_ROLES
    assert KnowledgeChunkRole.FAQ in ANSWERABLE_KNOWLEDGE_ROLES
    assert KnowledgeChunkRole.INSTRUCTION in ANSWERABLE_KNOWLEDGE_ROLES
    assert KnowledgeChunkRole.PRICE_LIST in ANSWERABLE_KNOWLEDGE_ROLES

    assert KnowledgeChunkRole.INTERNAL_EVAL_TEST in NON_ANSWER_KNOWLEDGE_ROLES
    assert KnowledgeChunkRole.RETRIEVAL_GUIDELINE in NON_ANSWER_KNOWLEDGE_ROLES
    assert KnowledgeChunkRole.NEGATIVE_TEST in NON_ANSWER_KNOWLEDGE_ROLES


def test_chunk_from_draft_is_typed_without_legacy_dict_contract() -> None:
    draft = KnowledgeChunkDraft(
        content="Refunds are reviewed by support.",
        role=KnowledgeChunkRole.FAQ,
        title="Refund policy",
        source_excerpt="Refunds are reviewed by support.",
        section_path=KnowledgeSectionPath(document_title="Docs", headings=("Refunds",)),
        questions=("Can I get a refund?",),
        synonyms=("refund",),
        tags=("billing",),
        embedding_text="Refund policy refund billing",
        metadata={"source": "upload"},
    )

    chunk = KnowledgeChunk.from_draft(
        project_id="project-1",
        document_id="document-1",
        draft=draft,
    )

    assert chunk.project_id == "project-1"
    assert chunk.document_id == "document-1"
    assert chunk.role == KnowledgeChunkRole.FAQ
    assert chunk.is_answerable is True
    assert chunk.title == "Refund policy"
    assert chunk.metadata["source"] == "upload"
    assert isinstance(chunk.metadata, MappingProxyType)


def test_new_domain_contract_does_not_contain_legacy_chunk_api() -> None:
    source = Path("src/domain/project_plane/knowledge_chunks.py").read_text(
        encoding="utf-8"
    )

    forbidden = (
        "JsonObject",
        "to_legacy_json",
        "from_legacy",
        "from_mapping",
        "entry_kind",
        "plain_enriched",
        '"chunk"',
        "'chunk'",
    )

    for marker in forbidden:
        assert marker not in source

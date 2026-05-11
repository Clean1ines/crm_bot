from __future__ import annotations

from types import MappingProxyType

import pytest
from typing import cast

from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunkDraft,
    KnowledgeChunkRole,
)
from src.domain.project_plane.knowledge_document_structure import (
    KnowledgeDocumentSource,
    ParsedKnowledgeDocument,
)


def test_document_source_requires_filename() -> None:
    with pytest.raises(ValueError, match="filename must not be empty"):
        KnowledgeDocumentSource(filename="   ")


def test_document_source_normalizes_fields() -> None:
    source = KnowledgeDocumentSource(
        filename="  docs.md  ",
        content_type=" text/markdown ",
        parser_name=" markdown ",
    )

    assert source.filename == "docs.md"
    assert source.content_type == "text/markdown"
    assert source.parser_name == "markdown"


def test_parsed_document_accepts_only_chunk_draft_tuple() -> None:
    with pytest.raises(TypeError, match="chunks must be a tuple"):
        ParsedKnowledgeDocument(
            source=KnowledgeDocumentSource(filename="docs.md"),
            chunks=cast(
                tuple[KnowledgeChunkDraft, ...],
                [KnowledgeChunkDraft(content="content")],
            ),
        )

    with pytest.raises(TypeError, match="KnowledgeChunkDraft"):
        ParsedKnowledgeDocument(
            source=KnowledgeDocumentSource(filename="docs.md"),
            chunks=cast(tuple[KnowledgeChunkDraft, ...], ("content",)),
        )


def test_parsed_document_exposes_answerable_chunks() -> None:
    answer = KnowledgeChunkDraft(
        content="Users can upload documents.",
        role=KnowledgeChunkRole.ANSWER_KNOWLEDGE,
    )
    internal = KnowledgeChunkDraft(
        content="Expected answer: users can upload documents.",
        role=KnowledgeChunkRole.INTERNAL_EVAL_TEST,
    )

    document = ParsedKnowledgeDocument(
        source=KnowledgeDocumentSource(filename="docs.md"),
        title=" Product docs ",
        chunks=(answer, internal),
        metadata={" source ": "upload"},
    )

    assert document.title == "Product docs"
    assert document.has_chunks is True
    assert document.answerable_chunks == (answer,)
    assert isinstance(document.metadata, MappingProxyType)
    assert document.metadata["source"] == "upload"

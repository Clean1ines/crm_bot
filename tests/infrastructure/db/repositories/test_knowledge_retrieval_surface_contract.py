from __future__ import annotations

import inspect

from src.domain.project_plane.knowledge_retrieval_surface import (
    FORBIDDEN_PRODUCTION_ENTRY_TYPES,
    TRANSITIONAL_PRODUCTION_ENTRY_TYPES,
)
from src.infrastructure.db.repositories.knowledge_repository import (
    ANSWERABLE_KNOWLEDGE_ENTRY_TYPES,
    KnowledgeRepository,
)
from src.infrastructure.db.repositories.rag_eval_repository import (
    RAG_EVAL_SOURCE_ENTRY_TYPES,
    RagEvalRepository,
)


def test_repository_runtime_entry_types_are_owned_by_retrieval_surface() -> None:
    assert ANSWERABLE_KNOWLEDGE_ENTRY_TYPES == tuple(
        sorted(TRANSITIONAL_PRODUCTION_ENTRY_TYPES)
    )
    assert RAG_EVAL_SOURCE_ENTRY_TYPES == tuple(
        sorted(TRANSITIONAL_PRODUCTION_ENTRY_TYPES)
    )

    assert not set(ANSWERABLE_KNOWLEDGE_ENTRY_TYPES).intersection(
        FORBIDDEN_PRODUCTION_ENTRY_TYPES
    )
    assert not set(RAG_EVAL_SOURCE_ENTRY_TYPES).intersection(
        FORBIDDEN_PRODUCTION_ENTRY_TYPES
    )


def test_runtime_search_queries_apply_surface_and_source_evidence_guard() -> None:
    search_source = inspect.getsource(KnowledgeRepository.search)
    preview_source = inspect.getsource(KnowledgeRepository.preview_search)

    for source in (search_source, preview_source):
        assert "kb.entry_type = ANY" in source
        assert "ANSWERABLE_KNOWLEDGE_ENTRY_TYPES" in source
        assert "kb.document_id IS NOT NULL" in source
        assert "NULLIF(btrim(kb.source_excerpt), '') IS NOT NULL" in source


def test_rag_eval_document_loader_applies_same_surface_and_source_guard() -> None:
    source = inspect.getsource(RagEvalRepository.load_document_chunks)

    assert "kb.entry_type = ANY" in source
    assert "RAG_EVAL_SOURCE_ENTRY_TYPES" in source
    assert "kb.document_id IS NOT NULL" in source
    assert "NULLIF(btrim(kb.source_excerpt), '') IS NOT NULL" in source

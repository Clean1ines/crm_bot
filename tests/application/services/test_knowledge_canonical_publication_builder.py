from __future__ import annotations

from pathlib import Path

import pytest

from src.application.errors import ValidationError
from src.application.services.knowledge_canonical_publication_builder import (
    canonical_entries_from_preprocessing_result,
)
from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingResult,
)


def _source_chunk(
    index: int,
    content: str,
    *,
    chunk_id: str | None = None,
) -> SourceChunk:
    return SourceChunk(
        id=chunk_id or f"doc:{index}",
        document_id="doc",
        project_id="project",
        source_index=index,
        content=content,
        start_offset=index * 100,
        end_offset=(index * 100) + len(content),
    )


def _result(
    *entries: KnowledgePreprocessingEntry,
    merged_counts: list[int] | None = None,
) -> KnowledgePreprocessingResult:
    return KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="test",
        model="test-model",
        entries=entries,
        metrics={
            "merged_preprocessing_entry_counts": merged_counts or [],
        },
    )


def _entry(
    *,
    title: str,
    answer: str,
    source_excerpt: str,
    question: str,
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        canonical_question=question,
        answer=answer,
        source_excerpt=source_excerpt,
        questions=(question,),
        synonyms=("crm",),
        tags=("faq",),
        embedding_text=f"{title} {answer}",
    )


def test_no_canonical_entry_without_source_refs() -> None:
    result = _result(
        _entry(
            title="No source",
            answer="Answer without source chunks",
            source_excerpt="Missing quote",
            question="Question?",
        )
    )

    with pytest.raises(ValidationError):
        canonical_entries_from_preprocessing_result(
            project_id="project",
            document_id="doc",
            compiler_run_id="run",
            result=result,
            source_chunks=(),
        )


def test_duplicate_guard_collapses_exact_answer_duplicates() -> None:
    result = _result(
        _entry(
            title="Refund",
            answer="Refund depends on project stage.",
            source_excerpt="Refund depends on project stage.",
            question="Can I get a refund?",
        ),
        _entry(
            title="Refund duplicate",
            answer="Refund depends on project stage.",
            source_excerpt="Refund depends on project stage. Extra policy note.",
            question="Can I get a refund?",
        ),
    )

    entries = canonical_entries_from_preprocessing_result(
        project_id="project",
        document_id="doc",
        compiler_run_id="run",
        result=result,
        source_chunks=(
            _source_chunk(0, "Refund depends on project stage."),
            _source_chunk(1, "Refund depends on project stage. Extra policy note."),
        ),
    )

    assert len(entries) == 1
    assert entries[0].metadata["publication_guard"] == "exact_fingerprint_collapse"
    assert entries[0].metadata["merged_candidate_count"] == 2


def test_source_refs_are_preserved_and_merged() -> None:
    result = _result(
        _entry(
            title="Support",
            answer="Support is available in chat.",
            source_excerpt="Support is available in chat.",
            question="Where is support?",
        ),
        _entry(
            title="Support duplicate",
            answer="Support is available in chat.",
            source_excerpt="Support is available by email too.",
            question="Where is support?",
        ),
    )

    entries = canonical_entries_from_preprocessing_result(
        project_id="project",
        document_id="doc",
        compiler_run_id="run",
        result=result,
        source_chunks=(
            _source_chunk(0, "Support is available in chat."),
            _source_chunk(1, "Support is available by email too."),
        ),
    )

    assert len(entries) == 1
    refs = entries[0].source_refs
    assert {ref.source_chunk_id for ref in refs} == {"doc:0", "doc:1"}
    assert {ref.quote for ref in refs} == {
        "Support is available in chat.",
        "Support is available by email too.",
    }


def test_stable_keys_are_unchanged_for_stage_k_publication() -> None:
    result = _result(
        _entry(
            title="Pricing",
            answer="Pricing depends on scope.",
            source_excerpt="Pricing depends on scope.",
            question="How much does it cost?",
        )
    )

    entries = canonical_entries_from_preprocessing_result(
        project_id="project",
        document_id="doc",
        compiler_run_id="run",
        result=result,
        source_chunks=(_source_chunk(0, "Pricing depends on scope."),),
    )

    assert len(entries) == 1
    assert entries[0].stable_key.startswith("doc:stage_k:")
    assert len(entries[0].stable_key) == len("doc:stage_k:") + 24


def test_ingestion_facade_no_longer_keeps_publication_aliases() -> None:
    ingestion_source = Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    builder_source = Path(
        "src/application/services/knowledge_canonical_publication_builder.py"
    ).read_text(encoding="utf-8")

    assert (
        "from src.application.services.knowledge_canonical_publication_builder import"
        not in (ingestion_source)
    )

    for marker in (
        "_canonical_entries_from_preprocessing_result",
        "_canonical_entries_from_raw_answer_candidates",
        "_source_refs_for_compiled_answer_draft",
        "_source_chunk_for_quote",
        "_final_publication_guard_collapse_exact_duplicates",
        "_merge_canonical_entries_structurally",
    ):
        assert marker not in ingestion_source

    assert "def canonical_entries_from_preprocessing_result(" in builder_source
    assert "def canonical_entries_from_raw_answer_candidates(" in builder_source
    assert "def _source_refs_for_compiled_answer_draft(" in builder_source
    assert "def _final_publication_guard_collapse_exact_duplicates(" in builder_source

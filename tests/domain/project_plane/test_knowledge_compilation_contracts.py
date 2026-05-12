from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    CompilerRun,
    EvalCase,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
)


def test_source_chunk_is_evidence_material_with_valid_source_index() -> None:
    chunk = SourceChunk(
        id="chunk-1",
        document_id="doc-1",
        project_id="project-1",
        source_index=0,
        content="Original source evidence.",
    )

    assert chunk.source_index == 0
    assert chunk.content == "Original source evidence."


def test_source_chunk_rejects_blank_content() -> None:
    with pytest.raises(ValueError, match="content"):
        SourceChunk(
            id="chunk-1",
            document_id="doc-1",
            project_id="project-1",
            source_index=0,
            content=" ",
        )


def test_source_ref_level_zero_grounding_requires_quote() -> None:
    ref = SourceRef(source_index=3, quote="  Exact evidence quote.  ")

    assert ref.quote == "Exact evidence quote."
    assert ref.is_grounded(minimum_level=0)
    assert ref.is_grounded(minimum_level=1)


def test_source_ref_level_one_grounding_requires_source_index() -> None:
    ref = SourceRef(quote="Exact evidence quote.")

    assert ref.is_grounded(minimum_level=0)
    assert not ref.is_grounded(minimum_level=1)


def test_enrichment_positive_surface_excludes_retrieval_guards() -> None:
    enrichment = KnowledgeEnrichment(
        questions=("How to order?", "How to order?"),
        synonyms=("buy",),
        tags=("orders",),
        retrieval_guards=("not about refunds",),
    )

    assert enrichment.questions == ("How to order?",)
    assert "not about refunds" not in enrichment.positive_query_surface


def test_canonical_entry_requires_source_refs_before_publication() -> None:
    entry = CanonicalKnowledgeEntry(
        id="entry-1",
        project_id="project-1",
        document_id="doc-1",
        compiler_run_id="run-1",
        stable_key="ordering",
        entry_kind=KnowledgeEntryKind.FAQ_ANSWER,
        title="Ordering",
        answer="Orders are accepted through Telegram.",
        source_refs=(),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
    )

    assert not entry.has_source_refs
    assert not entry.is_published_runtime_entry

    with pytest.raises(ValueError, match="source refs"):
        entry.assert_publishable()


def test_canonical_entry_with_source_ref_can_be_runtime_entry() -> None:
    entry = CanonicalKnowledgeEntry(
        id="entry-1",
        project_id="project-1",
        document_id="doc-1",
        compiler_run_id="run-1",
        stable_key="ordering",
        entry_kind=KnowledgeEntryKind.FAQ_ANSWER,
        title="Ordering",
        answer="Orders are accepted through Telegram.",
        source_refs=(SourceRef(source_index=0, quote="Orders through Telegram."),),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
    )

    assert entry.has_source_refs
    assert entry.is_published_runtime_entry
    entry.assert_publishable()


def test_eval_case_is_not_a_canonical_knowledge_entry() -> None:
    case = EvalCase(
        id="eval-1",
        project_id="project-1",
        document_id="doc-1",
        question="Can I order at night?",
        attack_type="time_trap",
    )

    assert not isinstance(case, CanonicalKnowledgeEntry)


def test_compiler_run_keeps_mode_as_strategy_not_entry_kind() -> None:
    run = CompilerRun(
        id="run-1",
        document_id="doc-1",
        project_id="project-1",
        mode="faq",
        compiler_version="kcd-v1",
    )

    assert run.mode == "faq"
    assert run.mode not in {kind.value for kind in KnowledgeEntryKind}

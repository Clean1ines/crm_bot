from __future__ import annotations

from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceRef,
)
from src.domain.project_plane.knowledge_retrieval_surface import (
    canonical_entry_eligibility,
    filter_canonical_runtime_entries,
    is_canonical_runtime_entry,
    is_compiler_mode_not_entry_kind,
    is_forbidden_runtime_artifact,
    is_runtime_entry_kind,
    is_transitional_runtime_row,
    transitional_runtime_row_eligibility,
)


def _entry(
    *,
    entry_kind: KnowledgeEntryKind = KnowledgeEntryKind.FAQ_ANSWER,
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.PUBLISHED,
    visibility: KnowledgeEntryVisibility = KnowledgeEntryVisibility.RUNTIME,
    source_refs: tuple[SourceRef, ...] = (
        SourceRef(source_index=0, quote="Source quote."),
    ),
) -> CanonicalKnowledgeEntry:
    return CanonicalKnowledgeEntry(
        id="entry-1",
        project_id="project-1",
        document_id="doc-1",
        compiler_run_id="run-1",
        stable_key="entry-1",
        entry_kind=entry_kind,
        title="Entry title",
        answer="Grounded answer.",
        source_refs=source_refs,
        status=status,
        visibility=visibility,
    )


def test_forbidden_artifacts_are_not_runtime_rows() -> None:
    for entry_type in (
        "internal_eval_test",
        "negative_test",
        "retrieval_guideline",
        "eval_question",
        "generated_question",
        "judge_prompt",
    ):
        assert is_forbidden_runtime_artifact(entry_type)
        assert not is_transitional_runtime_row(
            entry_type,
            has_source_evidence=True,
        )


def test_transitional_allowed_rows_require_source_evidence() -> None:
    assert is_transitional_runtime_row("faq", has_source_evidence=True)
    assert is_transitional_runtime_row("price_list", has_source_evidence=True)

    eligibility = transitional_runtime_row_eligibility(
        "faq",
        has_source_evidence=False,
    )

    assert not eligibility.allowed
    assert eligibility.reason == "source_evidence_required"


def test_raw_chunk_is_only_allowed_with_explicit_fallback_flag() -> None:
    assert not is_transitional_runtime_row("chunk", has_source_evidence=True)

    assert is_transitional_runtime_row(
        "chunk",
        has_source_evidence=True,
        fallback_raw_search_enabled=True,
    )


def test_compiler_modes_are_not_target_entry_kinds() -> None:
    assert is_compiler_mode_not_entry_kind("plain")
    assert is_compiler_mode_not_entry_kind("faq")
    assert is_compiler_mode_not_entry_kind("price_list")
    assert is_compiler_mode_not_entry_kind("instruction")

    assert not is_runtime_entry_kind("faq")
    assert not is_runtime_entry_kind("price_list")
    assert is_runtime_entry_kind("faq_answer")
    assert is_runtime_entry_kind("price_answer")


def test_published_runtime_canonical_entry_is_eligible() -> None:
    entry = _entry()

    eligibility = canonical_entry_eligibility(entry)

    assert eligibility.allowed
    assert eligibility.reason == "canonical_runtime_entry"
    assert is_canonical_runtime_entry(entry)


def test_hidden_or_draft_canonical_entries_are_not_eligible() -> None:
    hidden = _entry(visibility=KnowledgeEntryVisibility.HIDDEN)
    draft = _entry(status=KnowledgeEntryStatus.DRAFT)

    assert canonical_entry_eligibility(hidden).reason == "entry_not_runtime_visible"
    assert canonical_entry_eligibility(draft).reason == "entry_not_published"
    assert not is_canonical_runtime_entry(hidden)
    assert not is_canonical_runtime_entry(draft)


def test_canonical_entries_without_source_refs_are_not_eligible() -> None:
    entry = _entry(source_refs=())

    eligibility = canonical_entry_eligibility(entry)

    assert not eligibility.allowed
    assert eligibility.reason == "source_refs_required"


def test_fallback_canonical_entry_requires_explicit_fallback_mode() -> None:
    entry = _entry(entry_kind=KnowledgeEntryKind.FALLBACK_CHUNK)

    assert not is_canonical_runtime_entry(entry)
    assert is_canonical_runtime_entry(entry, fallback_raw_search_enabled=True)


def test_filter_canonical_runtime_entries_keeps_only_safe_entries() -> None:
    safe = _entry()
    hidden = _entry(visibility=KnowledgeEntryVisibility.HIDDEN)
    ungrounded = _entry(source_refs=())

    assert filter_canonical_runtime_entries((safe, hidden, ungrounded)) == (safe,)

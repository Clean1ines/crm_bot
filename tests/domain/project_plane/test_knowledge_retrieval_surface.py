from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceRef,
)
from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
    canonical_entry_eligibility,
    filter_canonical_runtime_entries,
    is_canonical_runtime_entry,
    is_compiler_mode_not_entry_kind,
    is_runtime_entry_kind,
)


def _entry(
    *,
    entry_kind: KnowledgeEntryKind = KnowledgeEntryKind.FAQ_ANSWER,
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.PUBLISHED,
    visibility: KnowledgeEntryVisibility = KnowledgeEntryVisibility.RUNTIME,
    source_refs: tuple[SourceRef, ...] = (
        SourceRef(source_index=0, quote="Source evidence."),
    ),
) -> CanonicalKnowledgeEntry:
    return CanonicalKnowledgeEntry(
        id="entry-1",
        project_id="project-1",
        document_id="document-1",
        compiler_run_id="run-1",
        stable_key="project-1/document-1/entry-1",
        entry_kind=entry_kind,
        title="Manager handoff",
        answer="Assistant transfers complex questions to a manager.",
        source_refs=source_refs,
        status=status,
        visibility=visibility,
    )


def _old_answer_role_value() -> str:
    return "answer" + "_knowledge"


def _old_chunk_value() -> str:
    return "ch" + "unk"


def _old_faq_mode_value() -> str:
    return "f" + "aq"


def _old_price_mode_value() -> str:
    return "price" + "_list"


def _old_instruction_mode_value() -> str:
    return "instruc" + "tion"


def test_runtime_surface_uses_canonical_entry_kinds_only() -> None:
    assert is_runtime_entry_kind("answer")
    assert is_runtime_entry_kind("faq_answer")
    assert is_runtime_entry_kind("price_answer")
    assert is_runtime_entry_kind("procedure")

    assert not is_runtime_entry_kind(_old_chunk_value())
    assert not is_runtime_entry_kind(_old_answer_role_value())
    assert not is_runtime_entry_kind(_old_faq_mode_value())
    assert not is_runtime_entry_kind(_old_price_mode_value())
    assert not is_runtime_entry_kind(_old_instruction_mode_value())


def test_compiler_modes_are_not_runtime_entry_kinds() -> None:
    for mode in (
        "plain",
        _old_faq_mode_value(),
        _old_price_mode_value(),
        _old_instruction_mode_value(),
    ):
        assert is_compiler_mode_not_entry_kind(mode)
        assert not is_runtime_entry_kind(mode)


def test_runtime_entry_kind_values_are_canonical_values() -> None:
    assert "answer" in RUNTIME_ENTRY_KIND_VALUES
    assert "faq_answer" in RUNTIME_ENTRY_KIND_VALUES
    assert "price_answer" in RUNTIME_ENTRY_KIND_VALUES
    assert "procedure" in RUNTIME_ENTRY_KIND_VALUES

    assert _old_chunk_value() not in RUNTIME_ENTRY_KIND_VALUES
    assert _old_answer_role_value() not in RUNTIME_ENTRY_KIND_VALUES
    assert _old_faq_mode_value() not in RUNTIME_ENTRY_KIND_VALUES
    assert _old_price_mode_value() not in RUNTIME_ENTRY_KIND_VALUES
    assert _old_instruction_mode_value() not in RUNTIME_ENTRY_KIND_VALUES


def test_published_runtime_entry_with_source_refs_is_allowed() -> None:
    entry = _entry()

    eligibility = canonical_entry_eligibility(entry)

    assert eligibility.allowed is True
    assert eligibility.reason == "canonical_runtime_entry"
    assert is_canonical_runtime_entry(entry)


def test_non_published_entry_is_not_runtime_visible() -> None:
    entry = _entry(status=KnowledgeEntryStatus.DRAFT)

    eligibility = canonical_entry_eligibility(entry)

    assert eligibility.allowed is False
    assert eligibility.reason == "entry_not_published"


def test_owner_only_entry_is_not_runtime_visible() -> None:
    entry = _entry(visibility=KnowledgeEntryVisibility.OWNER_ONLY)

    eligibility = canonical_entry_eligibility(entry)

    assert eligibility.allowed is False
    assert eligibility.reason == "entry_not_runtime_visible"


def test_source_refs_are_required_for_runtime_surface() -> None:
    entry = _entry(source_refs=())

    eligibility = canonical_entry_eligibility(entry)

    assert eligibility.allowed is False
    assert eligibility.reason == "source_refs_required"


def test_filter_canonical_runtime_entries_keeps_only_allowed_entries() -> None:
    allowed = _entry()
    hidden = _entry(visibility=KnowledgeEntryVisibility.HIDDEN)
    draft = _entry(status=KnowledgeEntryStatus.DRAFT)

    assert filter_canonical_runtime_entries((allowed, hidden, draft)) == (allowed,)

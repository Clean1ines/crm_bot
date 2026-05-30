from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INGESTION_SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
KNOWLEDGE_REPOSITORY = (
    ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"
)
KNOWLEDGE_PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"
DOCUMENT_PROCESSING_BLOCK = (
    ROOT / "frontend/src/pages/knowledge/components/DocumentProcessingBlock.tsx"
)
EN_LOCALE = ROOT / "frontend/src/shared/i18n/locales/en.ts"
RU_LOCALE = ROOT / "frontend/src/shared/i18n/locales/ru.ts"


def assert_any(source: str, candidates: tuple[str, ...], *, label: str) -> None:
    if not any(candidate in source for candidate in candidates):
        raise AssertionError(f"expected at least one {label} marker: {candidates}")


def test_kcd_stage_k7_answer_resolution_is_deterministic_and_evidence_aware() -> None:
    answer_resolution_source = (
        ROOT / "src/application/services/knowledge_answer_resolution_service.py"
    ).read_text(encoding="utf-8")
    structured_source = (
        ROOT / "src/application/services/knowledge_structured_ingestion_service.py"
    ).read_text(encoding="utf-8")
    canonical_publication_source = (
        ROOT / "src/application/services/knowledge_canonical_publication_builder.py"
    ).read_text(encoding="utf-8")
    combined = (
        answer_resolution_source
        + "\n"
        + structured_source
        + "\n"
        + canonical_publication_source
    )

    assert "_apply_answer_resolution_decisions" in answer_resolution_source
    assert "semantic_answer_resolution_count" in structured_source

    assert_any(
        combined,
        (
            "source_refs",
            "source_ref",
            "source_excerpt",
            "source_index",
            "source_indexes",
            "evidence",
        ),
        label="source evidence",
    )
    assert_any(
        combined,
        (
            "merged_entry_ids",
            "semantic_answer_resolution_count",
            "answer_resolution",
            "merge_count",
            "resolved_answer_count",
            "kept_separate_count",
        ),
        label="answer resolution accounting",
    )


def test_kcd_stage_k7_retighten_plan_reads_existing_document_entries() -> None:
    retighten_source = (
        ROOT / "src/application/services/knowledge_retighten_service.py"
    ).read_text(encoding="utf-8")
    answer_resolution_source = (
        ROOT / "src/application/services/knowledge_answer_resolution_service.py"
    ).read_text(encoding="utf-8")
    repository_source = KNOWLEDGE_REPOSITORY.read_text(encoding="utf-8")
    combined = (
        retighten_source + "\n" + answer_resolution_source + "\n" + repository_source
    )

    assert "plan_existing_document_retighten" in retighten_source
    assert "plan_deterministic_existing_document_retighten" in retighten_source
    assert (
        "current_entries = await repo.list_document_runtime_entries" in retighten_source
    )
    assert "build_preprocessing_entry_from_canonical_entry" in retighten_source
    assert "build_answer_resolution_cases_from_entries" in retighten_source
    assert "llm_call_count" in retighten_source

    assert_any(
        combined,
        (
            "list_document_runtime_entries",
            "list_entries_for_document",
            "list_entries",
            "get_document",
            "get_documents",
            "document_id",
        ),
        label="existing document entry loading",
    )


def test_kcd_stage_k7_progress_metrics_expose_technical_and_answer_counts() -> None:
    frontend_source = KNOWLEDGE_PAGE.read_text(encoding="utf-8")
    processing_block_source = DOCUMENT_PROCESSING_BLOCK.read_text(encoding="utf-8")
    frontend_components_source = f"{frontend_source}\n{processing_block_source}"
    en_locale = EN_LOCALE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")
    user_facing_source = f"{frontend_components_source}\n{en_locale}\n{ru_locale}"

    assert "processingDetailRows" in frontend_source
    assert "sourceChunkCount" in frontend_source
    assert "publishedEntries" in frontend_source
    assert "rawDrafts" in frontend_source
    assert "answerResolutionCases" in frontend_source
    assert "incomingAnswerCandidateCount" in frontend_source
    assert "appliedAnswerResolutions" in frontend_source

    assert_any(
        frontend_components_source,
        (
            "knowledge.document.sourceChunksPrefix",
            "knowledge.document.sourceChunks",
        ),
        label="source chunks progress i18n key",
    )
    assert_any(
        frontend_source,
        (
            "knowledge.document.publishedEntriesPrefix",
            "knowledge.document.publishedEntries",
        ),
        label="published entries progress i18n key",
    )
    assert_any(
        frontend_components_source,
        (
            "knowledge.document.incomingAnswersPrefix",
            "knowledge.document.incomingAnswers",
            "knowledge.document.incomingAnswerCandidates",
        ),
        label="incoming answer progress i18n key",
    )

    assert_any(
        user_facing_source,
        (
            "Published entries",
            "Published entries:",
        ),
        label="published entries user-facing label",
    )

    assert_any(
        ru_locale,
        (
            "'knowledge.document.sourceChunksPrefix': 'Технические фрагменты:'",
            "'knowledge.document.sourceChunks': 'Технические фрагменты: {count}'",
        ),
        label="Russian source chunks label",
    )
    assert_any(
        ru_locale,
        (
            "'knowledge.document.incomingAnswersPrefix': 'Новых кандидатов ответов на последнем этапе:'",
            "'knowledge.document.incomingAnswers': 'Новых кандидатов ответов на последнем этапе: {count}'",
            "'knowledge.document.incomingAnswerCandidates': 'Новых кандидатов ответов на последнем этапе: {count}'",
        ),
        label="Russian incoming answers label",
    )
    assert_any(
        ru_locale,
        (
            "'knowledge.document.answerResolutionsPrefix': 'Объединено ответов:'",
            "'knowledge.document.answerResolutions': 'Объединено ответов: {count}'",
            "'knowledge.document.answerResolutionsApplied': 'Объединений ответов применено: {count}'",
        ),
        label="Russian answer resolution label",
    )


def test_kcd_stage_k7_no_legacy_semantic_group_runtime_shortcut() -> None:
    source = INGESTION_SERVICE.read_text(encoding="utf-8")

    assert "semantic_group" not in source
    assert "semantic group" not in source.lower()

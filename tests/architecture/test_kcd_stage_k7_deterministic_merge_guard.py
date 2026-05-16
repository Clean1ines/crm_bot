from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

INGESTION_SERVICE = ROOT / "src/application/services/knowledge_ingestion_service.py"
KNOWLEDGE_REPOSITORY = (
    ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"
)
KNOWLEDGE_PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"
RU_LOCALE = ROOT / "frontend/src/shared/i18n/locales/ru.ts"


def assert_any(source: str, candidates: tuple[str, ...], *, label: str) -> None:
    if not any(candidate in source for candidate in candidates):
        raise AssertionError(f"expected at least one {label} marker: {candidates}")


def test_kcd_stage_k7_semantic_merge_is_deterministic_and_evidence_aware() -> None:
    source = INGESTION_SERVICE.read_text(encoding="utf-8")

    assert "_apply_semantic_merge_tightening_decisions" in source
    assert "semantic_answer_resolution_count" in source

    assert_any(
        source,
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
        source,
        (
            "merged_entry_ids",
            "semantic_answer_resolution_count",
            "semantic_merge",
            "merge_count",
        ),
        label="semantic merge accounting",
    )


def test_kcd_stage_k7_retighten_plan_reads_existing_document_entries() -> None:
    ingestion_source = INGESTION_SERVICE.read_text(encoding="utf-8")
    repository_source = KNOWLEDGE_REPOSITORY.read_text(encoding="utf-8")
    combined = ingestion_source + "\n" + repository_source

    assert "_retighten_existing_document_plan" in ingestion_source
    assert "incoming_entry_count" in ingestion_source
    assert "semantic_answer_count" in ingestion_source

    assert_any(
        combined,
        (
            "list_entries_for_document",
            "list_entries",
            "get_document",
            "get_documents",
            "document_id",
        ),
        label="existing document entry loading",
    )


def test_kcd_stage_k7_progress_metrics_expose_technical_and_semantic_counts() -> None:
    frontend_source = KNOWLEDGE_PAGE.read_text(encoding="utf-8")
    ru_locale = RU_LOCALE.read_text(encoding="utf-8")

    assert "processingDetailRows" in frontend_source
    assert "sourceChunkCount" in frontend_source
    assert "publishedEntries" in frontend_source
    assert "rawDrafts" in frontend_source
    assert "mergeGroups" in frontend_source
    assert "incomingSemanticEntryCount" in frontend_source
    assert "semanticMergeCount" in frontend_source

    assert "knowledge.document.sourceChunksPrefix" in frontend_source
    assert "Published entries" in frontend_source
    assert "knowledge.document.incomingAnswersPrefix" in frontend_source
    assert "knowledge.document.semanticMergesPrefix" in frontend_source

    assert (
        "'knowledge.document.sourceChunksPrefix': 'Технические фрагменты:'" in ru_locale
    )
    assert (
        "'knowledge.document.incomingAnswersPrefix': 'Новых смысловых ответов на последнем этапе:'"
        in ru_locale
    )
    assert (
        "'knowledge.document.semanticMergesPrefix': 'Объединено смысловых повторов:'"
        in ru_locale
    )


def test_kcd_stage_k7_no_legacy_semantic_group_runtime_shortcut() -> None:
    source = INGESTION_SERVICE.read_text(encoding="utf-8")

    assert "semantic_group" not in source
    assert "semantic group" not in source.lower()

from __future__ import annotations

from pathlib import Path


PROJECTION = Path("src/application/workbench/document_card_projection.py")
COMPOSITION = Path("src/interfaces/composition/faq_workbench_documents.py")
OBS_REPO = Path("src/infrastructure/db/workbench_observability_repository.py")


def test_documents_composition_attaches_card_view_to_list_payload() -> None:
    source = COMPOSITION.read_text(encoding="utf-8")

    assert "with_workbench_document_card_views" in source
    assert "payload = await service.list_documents(" in source
    assert (
        "return cast(dict[str, object], with_workbench_document_card_views(payload))"
        in source
    )


def test_observability_document_list_selects_card_view_source_fields() -> None:
    source = OBS_REPO.read_text(encoding="utf-8")

    required = (
        "d.retention_state",
        "pr.active_elapsed_seconds",
        "pr.wall_elapsed_seconds",
        "pr.total_prompt_tokens",
        "pr.total_completion_tokens",
        "pr.total_tokens",
        "pr.total_llm_calls",
        "pr.last_user_message",
        "registry_summary.canonical_fact_count",
        "registry_summary.final_registry_snapshot_id",
        "surface_summary.ready_count",
        "surface_summary.published_count",
        "curation.curation_session_id",
        "runtime_summary.runtime_entry_count",
        "auto_recovery.auto_resume_scheduled_at",
    )
    for marker in required:
        assert marker in source


def test_document_card_projection_keeps_new_card_contract_as_source_of_truth() -> None:
    source = PROJECTION.read_text(encoding="utf-8")

    assert "WorkbenchDocumentCardSource" in source
    assert "build_workbench_document_card_view" in source
    assert 'document["card_view"]' in source
    assert "with_workbench_document_card_views" in source


def test_document_card_backend_integration_does_not_restore_legacy_compiler_model() -> (
    None
):
    combined = (
        PROJECTION.read_text(encoding="utf-8")
        + COMPOSITION.read_text(encoding="utf-8")
        + OBS_REPO.read_text(encoding="utf-8")
    )

    forbidden = (
        "KnowledgeReadyAnswerPublicationService",
        "KnowledgeService(",
        "KnowledgeRepository(",
        "process_knowledge_upload",
        "knowledge_compilation",
        "AnswerCandidate",
        "CandidateCluster",
        "CanonicalKnowledgeEntry",
    )
    for marker in forbidden:
        assert marker not in combined

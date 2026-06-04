from __future__ import annotations

from pathlib import Path


API = Path("frontend/src/shared/api/modules/knowledge.ts")
CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")
PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")


def test_frontend_api_exposes_workbench_document_card_view_contract() -> None:
    source = API.read_text(encoding="utf-8")

    for marker in (
        "export type WorkbenchDocumentCardView",
        "WorkbenchDocumentCardActionView",
        "WorkbenchDocumentCardTimerView",
        "WorkbenchDocumentCardUsageView",
        "transient_purged",
        "resume_available",
    ):
        assert marker in source


def test_knowledge_document_card_prefers_backend_card_view() -> None:
    source = CARD.read_text(encoding="utf-8")

    assert "card_view?: WorkbenchDocumentCardView | null" in source
    assert "const cardView = doc.card_view ?? null" in source
    assert "cardView.status_i18n_key" in source
    assert "cardView.timer.active_elapsed_seconds" in source
    assert "cardView.usage.total_tokens" in source
    assert "cardView.messages.map" in source
    assert "cardView.actions.filter" in source
    assert "Промежуточные данные очищены" in source


def test_knowledge_document_card_old_ladder_is_fallback_only() -> None:
    source = CARD.read_text(encoding="utf-8")

    card_view_index = source.index("cardView ? (")
    fallback_index = source.index(": isDocumentProcessing ?")

    assert card_view_index < fallback_index
    assert "isDocumentProcessing ? (" in source
    assert "hasDrafts ? (" in source
    assert "hasSourceUnits ? (" in source


def test_knowledge_page_routes_card_actions_to_existing_mutations() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "onCardAction={(actionId)" in source
    assert 'actionId === "cancel_processing"' in source
    assert "cancelProcessingMutation.mutate(doc.id)" in source
    assert 'actionId === "resume_processing"' in source
    assert "resumeProcessingMutation.mutate(doc.id)" in source
    assert 'actionId === "publish_ready"' in source
    assert "publishReadyMutation.mutate(doc.id)" in source
    assert 'actionId === "open_curation"' in source
    assert "setCurationDocumentId(doc.id)" in source


def test_delete_modal_uses_card_view_confirmation_copy() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "deleteDocumentConfirmation" in source
    assert "default_confirmation" in source
    assert "{deleteDocumentConfirmation}" in source


def test_workbench_document_card_renders_fact_registry_result_metrics_not_surfaces() -> (
    None
):
    source = CARD.read_text(encoding="utf-8")

    assert "Факты:" in source
    assert "Runtime:" in source
    assert "Snapshot:" in source
    assert "cardView.registry.entry_count" in source
    assert "cardView.runtime.runtime_entry_count" in source
    assert "cardView.registry.final_snapshot_id" in source
    assert "Surfaces:" not in source


def test_workbench_document_card_explains_processing_in_human_terms() -> None:
    source = CARD.read_text(encoding="utf-8")

    assert "Что происходит с документом" in source
    assert "Прогресс" in source
    assert "sectionProgressPercent" in source
    assert "sectionProgressText" in source
    assert "elapsedText" in source
    assert "llmUsageText" in source
    assert "cardView.timer.active_elapsed_seconds" in source
    assert "cardView.timer.wall_elapsed_seconds" in source
    assert "cardView.usage.total_tokens" in source
    assert "cardView.usage.llm_call_count" in source
    assert "LLM-выз." in source


def test_document_card_does_not_mount_old_surface_compilation_summary() -> None:
    source = Path(
        "frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx"
    ).read_text(encoding="utf-8")

    forbidden = (
        "SurfaceCompilationSummary",
        "surfacePipelineContract",
        "knowledgeSurfaceApi",
        "@shared/api/modules/knowledgeSurface",
    )
    for marker in forbidden:
        assert marker not in source

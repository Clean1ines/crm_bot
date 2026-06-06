from pathlib import Path


CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")
PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")
API = Path("frontend/src/shared/api/modules/knowledge.ts")


def test_document_card_is_current_workbench_card_without_legacy_dependencies() -> None:
    source = CARD.read_text()

    for forbidden in (
        "ImportQualitySummary",
        "PriceFactsSummary",
        "CommercialTruthReviewSummary",
        "KnowledgeImportQualityReport",
        "KnowledgePriceFactsResponse",
        "KnowledgeCommercialTruthReviewResponse",
        "KnowledgeProcessingReport",
        "processingNode",
        "retightenReportNode",
        "actionsNode",
        "statusNode",
        "retighten",
        "retry_failed_batches",
        "Legacy",
        "старый прогресс",
        "Диагностика импорта",
        "unknown",
    ):
        assert forbidden not in source


def test_knowledge_page_calls_document_card_with_current_workbench_contract_only() -> (
    None
):
    source = PAGE.read_text()
    start = source.index("<KnowledgeDocumentCard")
    end = source.index("                />", start)
    call = source[start:end]

    for required in (
        "doc={doc}",
        "isDeletePending={",
        "onRequestDelete={",
        "onStopProcessing={",
        "onOpenCuration={",
        "onCardAction={",
        "formatSize={formatSize}",
        "knowledgeProcessingModeLabel={knowledgeProcessingModeLabel}",
    ):
        assert required in call

    for forbidden in (
        "processingReport=",
        "importQualityReport=",
        "priceFactsResponse=",
        "commercialTruthReviewResponse=",
        "processingNode=",
        "retightenReportNode=",
        "statusNode=",
        "actionsNode=",
        "hasDrafts=",
        "hasSourceUnits=",
        "unknown",
    ):
        assert forbidden not in call


def test_document_card_uses_backend_card_view_actions_for_lifecycle() -> None:
    source = CARD.read_text()

    assert "cardView.actions" in source
    assert "primaryActions(cardView)" in source
    assert "visibleSecondaryActions(cardView)" in source
    assert "handleCardAction(action)" in source
    assert "action.action_id === 'cancel_processing'" in source
    assert "action.action_id === 'open_curation'" in source
    assert "action.action_id === 'open_published_surfaces'" in source
    assert "action.action_id === 'delete_document'" in source


def test_document_card_keeps_current_design_and_user_visible_metrics() -> None:
    source = CARD.read_text()

    for marker in (
        "rounded-2xl bg-[var(--surface-elevated)] p-4",
        "Что происходит с документом",
        "active_elapsed_seconds",
        "wall_elapsed_seconds",
        "total_tokens",
        "llm_call_count",
        "sectionProgressPercent",
        "runtime_entry_count",
        "registry.entry_count",
        "Промежуточные данные очищены",
        "Локально извлечённые claims Prompt A",
    ):
        assert marker in source

    assert "Подробности обработки" not in source


def test_frontend_action_mapping_uses_current_workbench_action_ids() -> None:
    page = PAGE.read_text()
    api = API.read_text()

    for action_id in (
        "cancel_processing",
        "resume_processing",
        "publish_ready",
        "open_curation",
        "open_published_surfaces",
        "delete_document",
    ):
        assert action_id in api
        assert action_id in page

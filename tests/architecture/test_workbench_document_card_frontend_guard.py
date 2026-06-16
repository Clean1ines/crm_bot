from pathlib import Path


CARD = Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx")
PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")
API = Path("frontend/src/shared/api/modules/knowledge.ts")


def test_document_card_is_runtime_only_without_retired_frontend_contracts() -> None:
    source = CARD.read_text()

    for forbidden in (
        "WorkbenchDocumentCardView",
        "WorkbenchDocumentCardActionView",
        "WorkbenchDocumentCardUserMessage",
        "cardView",
        "card_view",
        "legacy",
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
        "старый прогресс",
        "Диагностика импорта",
        "liveTimerObservedAtMsRef",
    ):
        assert forbidden not in source


def test_knowledge_page_calls_document_card_with_runtime_contract_only() -> None:
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
        "workflowLiveState={",
        "workflowLiveStateLoading={",
        "workflowLiveStateError={",
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
    ):
        assert forbidden not in call


def test_document_card_uses_workflow_live_state_for_runtime_lifecycle() -> None:
    source = CARD.read_text()

    for marker in (
        "workflowLiveState",
        "workflow?.actions",
        "handleLiveAction(action)",
        "action.action_id === 'cancel_processing'",
        "action.action_id === 'open_curation'",
        "onRequestDelete",
        "workflow?.timeline",
        "liveTimelineEventLabel",
        "Последние события",
        "runtime-card-v1",
    ):
        assert marker in source


def test_document_card_keeps_runtime_user_visible_metrics() -> None:
    source = CARD.read_text()

    for marker in (
        "rounded-2xl bg-[var(--surface-elevated)] p-4",
        "Что происходит с документом",
        "active_elapsed_seconds",
        "total_tokens",
        "total_llm_calls",
        "sectionProgressPercent",
        "Подробности live-процесса",
        "Потоки секций",
        "LLM attempts",
        "Последние события",
    ):
        assert marker in source

    assert "wall_elapsed_seconds" not in source
    assert "liveWallElapsedSeconds" not in source
    assert " · всего " not in source
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


def test_knowledge_page_fetches_live_state_for_active_workbench_documents_without_card_artifacts() -> (
    None
):
    source = PAGE.read_text()

    assert "current_processing_run_id?: string | null;" in source
    assert "if (doc.current_processing_run_id) return true;" in source
    assert 'doc.status === "processing"' in source
    assert 'doc.status === "error"' in source
    assert '"auto_recovery_scheduled"' in source
    assert 'className="grid grid-cols-1 gap-6"' in source
    assert "!shouldFetchWorkflowLiveStateForDocument(doc)" in source

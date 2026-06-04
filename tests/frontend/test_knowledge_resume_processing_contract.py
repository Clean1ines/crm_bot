from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"
BLOCK = ROOT / "frontend/src/pages/knowledge/components/DocumentProcessingBlock.tsx"
API = ROOT / "frontend/src/shared/api/modules/knowledge.ts"


def test_resume_processing_button_and_api_are_wired() -> None:
    page = PAGE.read_text(encoding="utf-8")
    block = BLOCK.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")

    assert "resumeProcessing:" in api
    assert "/resume-processing" in api
    assert "resumeProcessingMutation" in page
    assert 'action.id === "resume_processing"' in page
    assert "resumeProcessingMutation.mutate(doc.id)" in page
    assert (
        "onResumeProcessing={() => resumeProcessingMutation.mutate(doc.id)}" not in page
    )
    assert "action.id === 'resume_processing'" in block
    assert "resumePending" in block
    assert "resumeTarget" in block


def test_processing_timer_uses_active_resume_window_not_original_upload_time() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "elapsed_before_resume_seconds" in page
    assert "processing_started_at_epoch" in page
    assert "elapsedBeforeResume" in page
    assert "nowMs / 1000" in page
    assert "processingStartedAtEpoch" in page


def test_knowledge_page_uses_processing_report_actions_for_primary_lifecycle_actions() -> (
    None
):
    page = PAGE.read_text(encoding="utf-8")

    assert "Legacy fallback only for display/status" in page
    assert 'enabledProcessingReportAction(processingReport, "cancel")' in page
    assert "enabledPrimaryProcessingReportActions(processingReport)" in page
    assert 'action.id === "resume_processing"' in page
    assert 'action.id === "publish_ready"' in page
    assert 'action.id === "retry_failed_batches"' not in page
    assert "retryFailedBatchesMutation" not in page
    assert "knowledgeApi.retryFailedBatches" not in page
    assert "isDocumentProcessing={canCancelProcessing}" in page
    assert "showStop={isDocumentProcessing(doc)}" not in page


def test_stopped_by_user_needle_is_legacy_fallback_not_resume_gate() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "STOPPED_BY_USER_ISSUE_NEEDLE" in page
    assert "Legacy fallback only for display/status" in page

    resume_action_index = page.index('action.id === "resume_processing"')
    stopped_needle_index = page.index("STOPPED_BY_USER_ISSUE_NEEDLE")
    legacy_comment_index = page.index("Legacy fallback only for display/status")

    assert legacy_comment_index < stopped_needle_index
    assert stopped_needle_index < resume_action_index

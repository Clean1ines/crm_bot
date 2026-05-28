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
    assert "onResumeProcessing={() => resumeProcessingMutation.mutate(doc.id)}" in page
    assert "action.id === 'resume_processing'" in block
    assert "resumePending" in block
    assert "resumeTarget" in block


def test_processing_timer_uses_active_resume_window_not_original_upload_time() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert "elapsed_before_resume_seconds" in page
    assert "processing_started_at_epoch" in page
    assert "elapsedBeforeResume + ((nowMs / 1000) - processingStartedAtEpoch)" in page

from __future__ import annotations

from pathlib import Path

from src.domain.project_plane.knowledge_document_lifecycle import (
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    TRIGGER_STALE_JOB_RECOVERY,
    TRIGGER_WORKER_RECOVERY,
)
from src.infrastructure.queue.handlers.knowledge_upload import (
    _knowledge_upload_lifecycle_trigger,
)

ROOT = Path(__file__).resolve().parents[4]
HANDLER = ROOT / "src/infrastructure/queue/handlers/knowledge_upload.py"


def test_knowledge_upload_handler_maps_job_source_to_lifecycle_trigger() -> None:
    assert _knowledge_upload_lifecycle_trigger(None) == TRIGGER_NORMAL_UPLOAD
    assert (
        _knowledge_upload_lifecycle_trigger("knowledge_document_resume")
        == TRIGGER_EXPLICIT_USER_RESUME
    )
    assert (
        _knowledge_upload_lifecycle_trigger("quota_recovery") == TRIGGER_QUOTA_RECOVERY
    )
    assert (
        _knowledge_upload_lifecycle_trigger("worker_recovery")
        == TRIGGER_WORKER_RECOVERY
    )
    assert (
        _knowledge_upload_lifecycle_trigger("stale_job_recovery")
        == TRIGGER_STALE_JOB_RECOVERY
    )
    assert _knowledge_upload_lifecycle_trigger("unknown") == TRIGGER_NORMAL_UPLOAD


def test_knowledge_upload_handler_forwards_resume_info_to_faq_ingestion() -> None:
    source = HANDLER.read_text(encoding="utf-8")

    assert "lifecycle_trigger=_knowledge_upload_lifecycle_trigger(dto.source)" in source
    assert "resume_run_id=dto.resume_run_id" in source

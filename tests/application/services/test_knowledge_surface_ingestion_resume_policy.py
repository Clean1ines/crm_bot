from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.knowledge_surface_ingestion_service import (
    _should_reuse_surface_run,
)
from src.domain.project_plane.knowledge_document_lifecycle import (
    LEGACY_USER_CANCELLED_MESSAGE,
    PROCESSING_PAUSED_QUOTA_STATUS,
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    TRIGGER_WORKER_RECOVERY,
    resolve_knowledge_document_lifecycle,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerRun,
    SurfaceCompilerRunStatus,
)


def _run(
    *,
    run_id: str = "run-1",
    status: SurfaceCompilerRunStatus = "cancelled",
    error_type: str | None = None,
) -> RetrievalSurfaceCompilerRun:
    return RetrievalSurfaceCompilerRun(
        id=run_id,
        project_id="project-1",
        document_id="document-1",
        mode="faq",
        status=status,
        compiler_kind="faq_retrieval_surface_compiler",
        model="test-model",
        prompt_version="faq_retrieval_surface_graph_v2",
        started_at=datetime.now(timezone.utc),
        error_type=error_type,
    )


def test_normal_upload_does_not_reuse_manual_cancelled_run() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        preprocessing_metrics={},
    )

    assert (
        _should_reuse_surface_run(
            latest_run=_run(status="cancelled", error_type="processing_cancelled"),
            lifecycle_trigger=TRIGGER_NORMAL_UPLOAD,
            resume_run_id=None,
            lifecycle_decision=decision,
            existing_document=None,
        )
        is False
    )


def test_explicit_user_resume_reuses_matching_cancelled_run() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        preprocessing_metrics={},
    )

    assert (
        _should_reuse_surface_run(
            latest_run=_run(status="cancelled", error_type="processing_cancelled"),
            lifecycle_trigger=TRIGGER_EXPLICIT_USER_RESUME,
            resume_run_id="run-1",
            lifecycle_decision=decision,
            existing_document=None,
        )
        is True
    )


def test_explicit_user_resume_rejects_wrong_resume_run_id() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        preprocessing_metrics={},
    )

    assert (
        _should_reuse_surface_run(
            latest_run=_run(status="cancelled", error_type="processing_cancelled"),
            lifecycle_trigger=TRIGGER_EXPLICIT_USER_RESUME,
            resume_run_id="other-run",
            lifecycle_decision=decision,
            existing_document=None,
        )
        is False
    )


def test_auto_recovery_reuses_quota_paused_failed_run_when_policy_allows() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status=PROCESSING_PAUSED_QUOTA_STATUS,
        preprocessing_status="failed",
        preprocessing_error="quota exhausted",
        preprocessing_metrics={"stage": PROCESSING_PAUSED_QUOTA_STATUS},
    )

    assert decision.can_auto_resume is True
    assert (
        _should_reuse_surface_run(
            latest_run=_run(status="failed", error_type="GroqFallbackExhaustedError"),
            lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
            resume_run_id=None,
            lifecycle_decision=decision,
            existing_document=None,
        )
        is True
    )


def test_auto_recovery_does_not_reuse_manual_cancelled_run() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        preprocessing_metrics={},
    )

    assert decision.can_auto_resume is False
    assert (
        _should_reuse_surface_run(
            latest_run=_run(status="cancelled", error_type="processing_cancelled"),
            lifecycle_trigger=TRIGGER_WORKER_RECOVERY,
            resume_run_id=None,
            lifecycle_decision=decision,
            existing_document=None,
        )
        is False
    )

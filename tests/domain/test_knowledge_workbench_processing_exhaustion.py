from __future__ import annotations

from datetime import datetime, timezone

from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    KnowledgeProcessingRun,
    ProcessingMethod,
    ProcessingRunStatus,
    ResumePolicy,
)
from src.domain.project_plane.knowledge_workbench.processing_exhaustion import (
    decide_processing_exhaustion_transition,
)


_NOW = datetime(2026, 5, 31, tzinfo=timezone.utc)


def _document(
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PROCESSING,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id="document-1",
        project_id="project-1",
        original_filename="faq.md",
        source_format="markdown",
        status=status,
        current_processing_run_id="processing-run-1",
        created_by_user_id="user-1",
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=_NOW if status is KnowledgeDocumentStatus.DELETED else None,
    )


def _run(
    status: ProcessingRunStatus = ProcessingRunStatus.RUNNING,
) -> KnowledgeProcessingRun:
    return KnowledgeProcessingRun(
        processing_run_id="processing-run-1",
        document_id="document-1",
        project_id="project-1",
        processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
        status=status,
        resume_policy=ResumePolicy.FORBIDDEN,
        started_by_user_id="user-1",
        started_at=_NOW,
        completed_at=None,
        deleted_at=_NOW if status is ProcessingRunStatus.DELETED else None,
    )


def test_quota_exhaustion_pauses_workbench_with_auto_recovery() -> None:
    transition = decide_processing_exhaustion_transition(
        document=_document(),
        processing_run=_run(),
        error_message="Groq 429 quota exhausted",
    )

    assert transition.document_status_after is KnowledgeDocumentStatus.PAUSED
    assert transition.processing_run_status_after is ProcessingRunStatus.PAUSED_QUOTA
    assert transition.resume_policy_after is ResumePolicy.AUTO_ALLOWED
    assert transition.automatic_recovery_allowed_after is True
    assert transition.error_kind == "quota_exhausted"


def test_provider_exhaustion_pauses_workbench_with_auto_recovery() -> None:
    transition = decide_processing_exhaustion_transition(
        document=_document(),
        processing_run=_run(),
        error_message="all fallbacks exhausted by provider",
    )

    assert transition.document_status_after is KnowledgeDocumentStatus.PAUSED
    assert transition.processing_run_status_after is ProcessingRunStatus.PAUSED_PROVIDER
    assert transition.resume_policy_after is ResumePolicy.AUTO_ALLOWED
    assert transition.automatic_recovery_allowed_after is True


def test_user_cancelled_run_is_not_reopened_by_exhaustion_hook() -> None:
    transition = decide_processing_exhaustion_transition(
        document=_document(status=KnowledgeDocumentStatus.CANCELLED),
        processing_run=_run(status=ProcessingRunStatus.CANCELLED_BY_USER),
        error_message="late worker failure",
    )

    assert transition.document_status_after is KnowledgeDocumentStatus.CANCELLED
    assert (
        transition.processing_run_status_after is ProcessingRunStatus.CANCELLED_BY_USER
    )
    assert transition.resume_policy_after is ResumePolicy.MANUAL_ONLY
    assert transition.automatic_recovery_allowed_after is False

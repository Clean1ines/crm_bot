from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeProcessingRun,
    ProcessingLifecycleTransitionKind,
    ProcessingMethod,
    ProcessingRunStatus,
    ProcessingTrigger,
    ResumePolicy,
    SourceType,
    decide_processing_cancel_transition,
    decide_processing_resume_or_recovery_transition,
    processing_lifecycle_transition_kind_for_trigger,
    is_processing_cancelled_for_workbench,
    resume_policy_for_status,
)


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


def _document(
    *,
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PROCESSING,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id="document-1",
        project_id="project-1",
        file_name="knowledge.md",
        source_type=SourceType.MARKDOWN,
        content_hash="hash-1",
        upload_id="upload-1",
        file_size_bytes=128,
        status=status,
        current_processing_run_id="processing-run-1",
        deleted_at=_now() if status is KnowledgeDocumentStatus.DELETED else None,
    )


def _run(
    *,
    status: ProcessingRunStatus = ProcessingRunStatus.RUNNING,
) -> KnowledgeProcessingRun:
    return KnowledgeProcessingRun(
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
        trigger=ProcessingTrigger.FRESH_UPLOAD,
        status=status,
        resume_policy=resume_policy_for_status(status),
        deleted_at=_now() if status is ProcessingRunStatus.DELETED else None,
    )


def test_cancel_transition_disables_automatic_recovery_and_requires_manual_resume() -> (
    None
):
    transition = decide_processing_cancel_transition(
        document=_document(status=KnowledgeDocumentStatus.PAUSED),
        existing_run=_run(status=ProcessingRunStatus.PAUSED_PROVIDER),
    )

    assert transition.kind is ProcessingLifecycleTransitionKind.USER_CANCEL
    assert transition.trigger is None
    assert transition.may_proceed is True
    assert transition.document_status_after is KnowledgeDocumentStatus.CANCELLED
    assert (
        transition.processing_run_status_after is ProcessingRunStatus.CANCELLED_BY_USER
    )
    assert transition.resume_policy_after is ResumePolicy.MANUAL_ONLY
    assert transition.automatic_recovery_allowed_after is False
    assert transition.requires_same_processing_run_id is True
    assert transition.reason == "explicit user cancellation disables automatic recovery"


def test_cancel_transition_rejects_failed_fatal_run_without_pretending_to_cancel() -> (
    None
):
    transition = decide_processing_cancel_transition(
        document=_document(),
        existing_run=_run(status=ProcessingRunStatus.FAILED_FATAL),
    )

    assert transition.kind is ProcessingLifecycleTransitionKind.USER_CANCEL
    assert transition.may_proceed is False
    assert transition.document_status_after is None
    assert transition.processing_run_status_after is None
    assert transition.resume_policy_after is ResumePolicy.FORBIDDEN
    assert transition.automatic_recovery_allowed_after is False
    assert "cannot be cancelled" in transition.reason


@pytest.mark.parametrize(
    ("trigger", "kind"),
    (
        (
            ProcessingTrigger.FRESH_UPLOAD,
            ProcessingLifecycleTransitionKind.FRESH_UPLOAD,
        ),
        (
            ProcessingTrigger.EXPLICIT_USER_RESUME,
            ProcessingLifecycleTransitionKind.EXPLICIT_USER_RESUME,
        ),
        (
            ProcessingTrigger.QUOTA_RECOVERY,
            ProcessingLifecycleTransitionKind.AUTO_RECOVERY,
        ),
        (
            ProcessingTrigger.PROVIDER_RECOVERY,
            ProcessingLifecycleTransitionKind.AUTO_RECOVERY,
        ),
        (
            ProcessingTrigger.SERVER_RECOVERY,
            ProcessingLifecycleTransitionKind.AUTO_RECOVERY,
        ),
    ),
)
def test_trigger_maps_to_lifecycle_transition_kind(
    trigger: ProcessingTrigger,
    kind: ProcessingLifecycleTransitionKind,
) -> None:
    assert processing_lifecycle_transition_kind_for_trigger(trigger) is kind


def test_explicit_user_resume_transition_preserves_manual_only_policy() -> None:
    transition = decide_processing_resume_or_recovery_transition(
        trigger=ProcessingTrigger.EXPLICIT_USER_RESUME,
        document=_document(status=KnowledgeDocumentStatus.CANCELLED),
        requested_processing_run_id="processing-run-1",
        existing_run=_run(status=ProcessingRunStatus.CANCELLED_BY_USER),
    )

    assert transition.kind is ProcessingLifecycleTransitionKind.EXPLICIT_USER_RESUME
    assert transition.trigger is ProcessingTrigger.EXPLICIT_USER_RESUME
    assert transition.may_proceed is True
    assert transition.resume_policy_after is ResumePolicy.MANUAL_ONLY
    assert transition.automatic_recovery_allowed_after is False
    assert transition.requires_same_processing_run_id is True
    assert transition.reason == (
        "explicit user resume may resume only manual-only cancelled runs"
    )


def test_auto_recovery_transition_preserves_auto_allowed_policy() -> None:
    transition = decide_processing_resume_or_recovery_transition(
        trigger=ProcessingTrigger.PROVIDER_RECOVERY,
        document=_document(status=KnowledgeDocumentStatus.PAUSED),
        requested_processing_run_id="processing-run-1",
        existing_run=_run(status=ProcessingRunStatus.PAUSED_PROVIDER),
    )

    assert transition.kind is ProcessingLifecycleTransitionKind.AUTO_RECOVERY
    assert transition.trigger is ProcessingTrigger.PROVIDER_RECOVERY
    assert transition.may_proceed is True
    assert transition.resume_policy_after is ResumePolicy.AUTO_ALLOWED
    assert transition.automatic_recovery_allowed_after is True
    assert transition.requires_same_processing_run_id is True
    assert transition.reason == (
        "automatic recovery may resume only auto-allowed paused runs"
    )


def test_auto_recovery_transition_rejects_user_cancelled_run() -> None:
    transition = decide_processing_resume_or_recovery_transition(
        trigger=ProcessingTrigger.PROVIDER_RECOVERY,
        document=_document(status=KnowledgeDocumentStatus.CANCELLED),
        requested_processing_run_id="processing-run-1",
        existing_run=_run(status=ProcessingRunStatus.CANCELLED_BY_USER),
    )

    assert transition.kind is ProcessingLifecycleTransitionKind.AUTO_RECOVERY
    assert transition.may_proceed is False
    assert transition.resume_policy_after is ResumePolicy.MANUAL_ONLY
    assert transition.automatic_recovery_allowed_after is False
    assert transition.reason == (
        "automatic recovery may resume only auto-allowed paused runs"
    )


def test_fresh_upload_transition_stays_new_lineage_not_resume() -> None:
    transition = decide_processing_resume_or_recovery_transition(
        trigger=ProcessingTrigger.FRESH_UPLOAD,
        document=_document(status=KnowledgeDocumentStatus.UPLOADED),
        requested_processing_run_id=None,
        existing_run=None,
    )

    assert transition.kind is ProcessingLifecycleTransitionKind.FRESH_UPLOAD
    assert transition.trigger is ProcessingTrigger.FRESH_UPLOAD
    assert transition.may_proceed is False
    assert transition.resume_policy_after is ResumePolicy.FORBIDDEN
    assert transition.automatic_recovery_allowed_after is False
    assert transition.requires_same_processing_run_id is False
    assert transition.reason == "fresh upload always starts a new processing lineage"


def test_workbench_processing_cancelled_helper_detects_document_or_run_cancel() -> None:
    assert (
        is_processing_cancelled_for_workbench(
            document=_document(status=KnowledgeDocumentStatus.CANCELLED),
            processing_run=_run(status=ProcessingRunStatus.RUNNING),
        )
        is True
    )
    assert (
        is_processing_cancelled_for_workbench(
            document=_document(status=KnowledgeDocumentStatus.PROCESSING),
            processing_run=_run(status=ProcessingRunStatus.CANCELLED_BY_USER),
        )
        is True
    )
    assert (
        is_processing_cancelled_for_workbench(
            document=_document(status=KnowledgeDocumentStatus.PROCESSING),
            processing_run=_run(status=ProcessingRunStatus.RUNNING),
        )
        is False
    )


def test_workbench_processing_cancelled_helper_detects_deleted_document_or_run() -> (
    None
):
    assert (
        is_processing_cancelled_for_workbench(
            document=_document(status=KnowledgeDocumentStatus.DELETED),
            processing_run=_run(status=ProcessingRunStatus.RUNNING),
        )
        is True
    )
    assert (
        is_processing_cancelled_for_workbench(
            document=_document(status=KnowledgeDocumentStatus.PROCESSING),
            processing_run=_run(status=ProcessingRunStatus.DELETED),
        )
        is True
    )

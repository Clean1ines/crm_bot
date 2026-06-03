from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    DomainInvariantError,
    KnowledgeProcessingRun,
    ProcessingMethod,
    ProcessingRunStatus,
    ProcessingTrigger,
    ResumePolicy,
    SourceType,
    decide_processing_cancellation,
    resume_policy_for_status,
)


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


def _existing_processing_run_statuses(
    *names: str,
) -> tuple[ProcessingRunStatus, ...]:
    return tuple(
        member
        for name in names
        if isinstance(
            member := getattr(ProcessingRunStatus, name, None),
            ProcessingRunStatus,
        )
    )


def _existing_document_statuses(
    *names: str,
) -> tuple[KnowledgeDocumentStatus, ...]:
    return tuple(
        member
        for name in names
        if isinstance(
            member := getattr(KnowledgeDocumentStatus, name, None),
            KnowledgeDocumentStatus,
        )
    )


CANCELLABLE_RUN_STATUSES = _existing_processing_run_statuses(
    "PENDING",
    "RUNNING",
    "PAUSING",
    "PAUSED_QUOTA",
    "PAUSED_PROVIDER",
    "PAUSED_SERVER_INTERRUPTED",
)

REJECTED_RUN_STATUSES = _existing_processing_run_statuses(
    "COMPLETED",
    "CANCELLED_BY_USER",
    "FAILED_VALIDATION",
    "FAILED_FATAL",
    "DELETED",
)

CANCELLABLE_DOCUMENT_STATUSES = _existing_document_statuses(
    "UPLOADED",
    "SECTIONED",
    "PROCESSING",
    "PARTIALLY_PROCESSED",
    "PAUSED",
)

REJECTED_DOCUMENT_STATUSES = _existing_document_statuses(
    "PROCESSED",
    "CANCELLED",
    "FAILED",
    "DELETED",
)


def _document(
    *,
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PROCESSING,
    document_id: str = "document-1",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=document_id,
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
    document_id: str = "document-1",
) -> KnowledgeProcessingRun:
    return KnowledgeProcessingRun(
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id=document_id,
        processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
        trigger=ProcessingTrigger.FRESH_UPLOAD,
        status=status,
        resume_policy=resume_policy_for_status(status),
        deleted_at=_now() if status is ProcessingRunStatus.DELETED else None,
    )


@pytest.mark.parametrize("run_status", CANCELLABLE_RUN_STATUSES)
def test_cancellation_converts_active_or_auto_recoverable_run_to_manual_resume(
    run_status: ProcessingRunStatus,
) -> None:
    decision = decide_processing_cancellation(
        document=_document(),
        existing_run=_run(status=run_status),
    )

    assert decision.may_cancel is True
    assert decision.document_status is KnowledgeDocumentStatus.CANCELLED
    assert decision.processing_run_status is ProcessingRunStatus.CANCELLED_BY_USER
    assert decision.resume_policy is ResumePolicy.MANUAL_ONLY
    assert decision.reason == "explicit user cancellation disables automatic recovery"


@pytest.mark.parametrize("document_status", CANCELLABLE_DOCUMENT_STATUSES)
def test_cancellation_allows_cancellable_document_states(
    document_status: KnowledgeDocumentStatus,
) -> None:
    decision = decide_processing_cancellation(
        document=_document(status=document_status),
        existing_run=_run(status=ProcessingRunStatus.RUNNING),
    )

    assert decision.may_cancel is True
    assert decision.document_status is KnowledgeDocumentStatus.CANCELLED
    assert decision.processing_run_status is ProcessingRunStatus.CANCELLED_BY_USER
    assert decision.resume_policy is ResumePolicy.MANUAL_ONLY


@pytest.mark.parametrize("run_status", REJECTED_RUN_STATUSES)
def test_cancellation_rejects_terminal_or_failed_run_states(
    run_status: ProcessingRunStatus,
) -> None:
    decision = decide_processing_cancellation(
        document=_document(),
        existing_run=_run(status=run_status),
    )

    assert decision.may_cancel is False
    assert decision.document_status is None
    assert decision.processing_run_status is None
    assert decision.resume_policy is resume_policy_for_status(run_status)
    assert "processing run cannot be cancelled from status" in decision.reason


@pytest.mark.parametrize("document_status", REJECTED_DOCUMENT_STATUSES)
def test_cancellation_rejects_terminal_document_states(
    document_status: KnowledgeDocumentStatus,
) -> None:
    decision = decide_processing_cancellation(
        document=_document(status=document_status),
        existing_run=_run(),
    )

    assert decision.may_cancel is False
    assert decision.document_status is None
    assert decision.processing_run_status is None


def test_cancellation_rejects_missing_processing_run() -> None:
    decision = decide_processing_cancellation(
        document=_document(),
        existing_run=None,
    )

    assert decision.may_cancel is False
    assert decision.resume_policy is ResumePolicy.FORBIDDEN
    assert decision.reason == "cancellation requires an existing processing run"


def test_cancellation_rejects_wrong_document_run_pair() -> None:
    decision = decide_processing_cancellation(
        document=_document(document_id="document-1"),
        existing_run=_run(document_id="other-document"),
    )

    assert decision.may_cancel is False
    assert decision.reason == "cancellation requires the same document_id"


def test_cancelled_by_user_still_maps_to_manual_resume_policy() -> None:
    assert (
        resume_policy_for_status(ProcessingRunStatus.CANCELLED_BY_USER)
        is ResumePolicy.MANUAL_ONLY
    )


@pytest.mark.parametrize(
    "run_status",
    _existing_processing_run_statuses(
        "PAUSED_QUOTA",
        "PAUSED_PROVIDER",
        "PAUSED_SERVER_INTERRUPTED",
    ),
)
def test_cancel_overrides_auto_recovery_states_to_manual_resume(
    run_status: ProcessingRunStatus,
) -> None:
    assert resume_policy_for_status(run_status) is ResumePolicy.AUTO_ALLOWED

    decision = decide_processing_cancellation(
        document=_document(status=KnowledgeDocumentStatus.PAUSED),
        existing_run=_run(status=run_status),
    )

    assert decision.may_cancel is True
    assert decision.processing_run_status is ProcessingRunStatus.CANCELLED_BY_USER
    assert decision.resume_policy is ResumePolicy.MANUAL_ONLY


def test_fresh_upload_run_can_become_auto_recoverable_after_start() -> None:
    run = KnowledgeProcessingRun(
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
        trigger=ProcessingTrigger.FRESH_UPLOAD,
        status=ProcessingRunStatus.PAUSED_QUOTA,
        resume_policy=ResumePolicy.AUTO_ALLOWED,
    )

    assert run.status is ProcessingRunStatus.PAUSED_QUOTA
    assert run.resume_policy is ResumePolicy.AUTO_ALLOWED


def test_fresh_upload_run_can_become_manual_only_after_user_cancel() -> None:
    run = KnowledgeProcessingRun(
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
        trigger=ProcessingTrigger.FRESH_UPLOAD,
        status=ProcessingRunStatus.CANCELLED_BY_USER,
        resume_policy=ResumePolicy.MANUAL_ONLY,
    )

    assert run.status is ProcessingRunStatus.CANCELLED_BY_USER
    assert run.resume_policy is ResumePolicy.MANUAL_ONLY


def test_fresh_upload_active_run_still_cannot_start_with_resumable_policy() -> None:
    with pytest.raises(
        DomainInvariantError,
        match="fresh_upload run cannot start with resumable policy",
    ):
        KnowledgeProcessingRun(
            processing_run_id="processing-run-1",
            project_id="project-1",
            document_id="document-1",
            processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
            trigger=ProcessingTrigger.FRESH_UPLOAD,
            status=ProcessingRunStatus.RUNNING,
            resume_policy=ResumePolicy.AUTO_ALLOWED,
        )

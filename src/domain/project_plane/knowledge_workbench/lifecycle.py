from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    KnowledgeProcessingRun,
    ProcessingRunStatus,
    ProcessingTrigger,
    ResumePolicy,
    decide_processing_cancellation,
    decide_processing_lifecycle,
)


class ProcessingLifecycleTransitionKind(StrEnum):
    FRESH_UPLOAD = "fresh_upload"
    EXPLICIT_USER_RESUME = "explicit_user_resume"
    AUTO_RECOVERY = "auto_recovery"
    USER_CANCEL = "user_cancel"
    MANUAL_REPROCESS = "manual_reprocess"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class ProcessingLifecycleTransition:
    kind: ProcessingLifecycleTransitionKind
    trigger: ProcessingTrigger | None
    may_proceed: bool
    document_status_after: KnowledgeDocumentStatus | None
    processing_run_status_after: ProcessingRunStatus | None
    resume_policy_after: ResumePolicy
    automatic_recovery_allowed_after: bool
    requires_same_processing_run_id: bool
    reason: str


def processing_lifecycle_transition_kind_for_trigger(
    trigger: ProcessingTrigger,
) -> ProcessingLifecycleTransitionKind:
    if trigger is ProcessingTrigger.FRESH_UPLOAD:
        return ProcessingLifecycleTransitionKind.FRESH_UPLOAD

    if trigger is ProcessingTrigger.EXPLICIT_USER_RESUME:
        return ProcessingLifecycleTransitionKind.EXPLICIT_USER_RESUME

    if trigger in {
        ProcessingTrigger.QUOTA_RECOVERY,
        ProcessingTrigger.PROVIDER_RECOVERY,
        ProcessingTrigger.SERVER_RECOVERY,
    }:
        return ProcessingLifecycleTransitionKind.AUTO_RECOVERY

    manual_reprocess = getattr(ProcessingTrigger, "MANUAL_REPROCESS", None)
    if manual_reprocess is not None and trigger is manual_reprocess:
        return ProcessingLifecycleTransitionKind.MANUAL_REPROCESS

    return ProcessingLifecycleTransitionKind.UNSUPPORTED


def decide_processing_resume_or_recovery_transition(
    *,
    trigger: ProcessingTrigger,
    document: KnowledgeDocument,
    requested_processing_run_id: str | None,
    existing_run: KnowledgeProcessingRun | None,
) -> ProcessingLifecycleTransition:
    decision = decide_processing_lifecycle(
        trigger=trigger,
        document=document,
        requested_processing_run_id=requested_processing_run_id,
        existing_run=existing_run,
    )
    return ProcessingLifecycleTransition(
        kind=processing_lifecycle_transition_kind_for_trigger(trigger),
        trigger=trigger,
        may_proceed=decision.may_resume,
        document_status_after=None,
        processing_run_status_after=None,
        resume_policy_after=decision.resume_policy,
        automatic_recovery_allowed_after=(
            decision.may_resume and decision.resume_policy is ResumePolicy.AUTO_ALLOWED
        ),
        requires_same_processing_run_id=decision.requires_same_processing_run_id,
        reason=decision.reason,
    )


def decide_processing_cancel_transition(
    *,
    document: KnowledgeDocument,
    existing_run: KnowledgeProcessingRun | None,
) -> ProcessingLifecycleTransition:
    decision = decide_processing_cancellation(
        document=document,
        existing_run=existing_run,
    )
    return ProcessingLifecycleTransition(
        kind=ProcessingLifecycleTransitionKind.USER_CANCEL,
        trigger=None,
        may_proceed=decision.may_cancel,
        document_status_after=decision.document_status,
        processing_run_status_after=decision.processing_run_status,
        resume_policy_after=decision.resume_policy,
        automatic_recovery_allowed_after=False,
        requires_same_processing_run_id=True,
        reason=decision.reason,
    )


def is_processing_cancelled_for_workbench(
    *,
    document: KnowledgeDocument,
    processing_run: KnowledgeProcessingRun,
) -> bool:
    return (
        document.status is KnowledgeDocumentStatus.CANCELLED
        or document.status is KnowledgeDocumentStatus.DELETED
        or processing_run.status is ProcessingRunStatus.CANCELLED_BY_USER
        or processing_run.status is ProcessingRunStatus.DELETED
    )


__all__ = [
    "ProcessingLifecycleTransition",
    "ProcessingLifecycleTransitionKind",
    "decide_processing_cancel_transition",
    "decide_processing_resume_or_recovery_transition",
    "processing_lifecycle_transition_kind_for_trigger",
    "is_processing_cancelled_for_workbench",
]

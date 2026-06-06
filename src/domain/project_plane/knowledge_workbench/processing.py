from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .documents import (
    KnowledgeDocument,
    ensure_document_can_be_resumed,
    KnowledgeDocumentStatus,
)
from .shared import (
    DocumentId,
    DomainInvariantError,
    ErrorReportId,
    ProcessingRunId,
    ProjectId,
    require_document_id,
    require_processing_run_id,
    require_project_id,
)


class ProcessingMethod(StrEnum):
    FAQ_SECTION_REGISTRY_V1 = "faq_section_registry_v1"
    PRICE_LIST_V1 = "price_list_v1"
    INSTRUCTION_V1 = "instruction_v1"
    PLAIN_LEGACY = "plain_legacy"


class ProcessingTrigger(StrEnum):
    FRESH_UPLOAD = "fresh_upload"
    EXPLICIT_USER_RESUME = "explicit_user_resume"
    QUOTA_RECOVERY = "quota_recovery"
    PROVIDER_RECOVERY = "provider_recovery"
    SERVER_RECOVERY = "server_recovery"
    MANUAL_REPROCESS = "manual_reprocess"


class ProcessingRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED_QUOTA = "paused_quota"
    PAUSED_PROVIDER = "paused_provider"
    PAUSED_SERVER_INTERRUPTED = "paused_server_interrupted"
    CANCELLING = "cancelling"
    CANCELLED_BY_USER = "cancelled_by_user"
    COMPLETED = "completed"
    FAILED_VALIDATION = "failed_validation"
    FAILED_FATAL = "failed_fatal"
    DELETED = "deleted"


class ResumePolicy(StrEnum):
    FORBIDDEN = "forbidden"
    MANUAL_ONLY = "manual_only"
    AUTO_ALLOWED = "auto_allowed"


@dataclass(frozen=True, slots=True)
class KnowledgeProcessingRun:
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    processing_method: ProcessingMethod
    trigger: ProcessingTrigger
    status: ProcessingRunStatus
    resume_policy: ResumePolicy
    started_at: datetime | None = None
    current_active_started_at: datetime | None = None
    stopped_at: datetime | None = None
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    active_elapsed_seconds: int = 0
    wall_elapsed_seconds: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    last_error_kind: str | None = None
    last_error_report_id: ErrorReportId | None = None
    last_user_message: str | None = None
    last_internal_error: str | None = None

    def __post_init__(self) -> None:
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        require_processing_run_id(self.processing_run_id)
        if self.total_tokens != self.total_prompt_tokens + self.total_completion_tokens:
            raise DomainInvariantError(
                "total_tokens must equal prompt + completion tokens"
            )
        if self.status is ProcessingRunStatus.DELETED and self.deleted_at is None:
            raise DomainInvariantError("deleted processing run must have deleted_at")
        if (
            self.current_active_started_at is not None
            and self.started_at is not None
            and self.current_active_started_at < self.started_at
        ):
            raise DomainInvariantError(
                "current_active_started_at cannot be before started_at"
            )
        if self.active_elapsed_seconds < 0:
            raise DomainInvariantError("active_elapsed_seconds must be non-negative")
        if self.wall_elapsed_seconds < 0:
            raise DomainInvariantError("wall_elapsed_seconds must be non-negative")
        if (
            self.trigger is ProcessingTrigger.FRESH_UPLOAD
            and self.status
            in {
                ProcessingRunStatus.PENDING,
                ProcessingRunStatus.RUNNING,
            }
            and self.resume_policy is not ResumePolicy.FORBIDDEN
        ):
            raise DomainInvariantError(
                "fresh_upload run cannot start with resumable policy"
            )


@dataclass(frozen=True, slots=True)
class ProcessingLifecycleDecision:
    trigger: ProcessingTrigger
    resume_policy: ResumePolicy
    may_resume: bool
    requires_same_processing_run_id: bool
    reason: str


def resume_policy_for_status(status: ProcessingRunStatus) -> ResumePolicy:
    if status is ProcessingRunStatus.CANCELLED_BY_USER:
        return ResumePolicy.MANUAL_ONLY
    if status in {
        ProcessingRunStatus.PAUSED_QUOTA,
        ProcessingRunStatus.PAUSED_PROVIDER,
        ProcessingRunStatus.PAUSED_SERVER_INTERRUPTED,
    }:
        return ResumePolicy.AUTO_ALLOWED
    if status in {
        ProcessingRunStatus.FAILED_VALIDATION,
        ProcessingRunStatus.FAILED_FATAL,
        ProcessingRunStatus.DELETED,
        ProcessingRunStatus.COMPLETED,
    }:
        return ResumePolicy.FORBIDDEN
    return ResumePolicy.FORBIDDEN


def decide_processing_lifecycle(
    *,
    trigger: ProcessingTrigger,
    document: KnowledgeDocument,
    requested_processing_run_id: ProcessingRunId | None,
    existing_run: KnowledgeProcessingRun | None,
) -> ProcessingLifecycleDecision:
    if trigger is ProcessingTrigger.FRESH_UPLOAD:
        return ProcessingLifecycleDecision(
            trigger=trigger,
            resume_policy=ResumePolicy.FORBIDDEN,
            may_resume=False,
            requires_same_processing_run_id=False,
            reason="fresh upload always starts a new processing lineage",
        )

    ensure_document_can_be_resumed(document)

    if existing_run is None:
        return ProcessingLifecycleDecision(
            trigger=trigger,
            resume_policy=ResumePolicy.FORBIDDEN,
            may_resume=False,
            requires_same_processing_run_id=True,
            reason="resume requested but no existing run was provided",
        )

    if existing_run.document_id != document.document_id:
        return ProcessingLifecycleDecision(
            trigger=trigger,
            resume_policy=ResumePolicy.FORBIDDEN,
            may_resume=False,
            requires_same_processing_run_id=True,
            reason="resume requires the same document_id",
        )

    if requested_processing_run_id != existing_run.processing_run_id:
        return ProcessingLifecycleDecision(
            trigger=trigger,
            resume_policy=ResumePolicy.FORBIDDEN,
            may_resume=False,
            requires_same_processing_run_id=True,
            reason="resume requires explicit same processing_run_id",
        )

    policy = resume_policy_for_status(existing_run.status)

    if trigger is ProcessingTrigger.EXPLICIT_USER_RESUME:
        return ProcessingLifecycleDecision(
            trigger=trigger,
            resume_policy=policy,
            may_resume=policy is ResumePolicy.MANUAL_ONLY,
            requires_same_processing_run_id=True,
            reason="explicit user resume may resume only manual-only cancelled runs",
        )

    if trigger in {
        ProcessingTrigger.QUOTA_RECOVERY,
        ProcessingTrigger.PROVIDER_RECOVERY,
        ProcessingTrigger.SERVER_RECOVERY,
    }:
        return ProcessingLifecycleDecision(
            trigger=trigger,
            resume_policy=policy,
            may_resume=policy is ResumePolicy.AUTO_ALLOWED,
            requires_same_processing_run_id=True,
            reason="automatic recovery may resume only auto-allowed paused runs",
        )

    return ProcessingLifecycleDecision(
        trigger=trigger,
        resume_policy=ResumePolicy.FORBIDDEN,
        may_resume=False,
        requires_same_processing_run_id=True,
        reason="trigger does not allow resume",
    )


@dataclass(frozen=True, slots=True)
class ProcessingCancellationDecision:
    may_cancel: bool
    document_status: KnowledgeDocumentStatus | None
    processing_run_status: ProcessingRunStatus | None
    resume_policy: ResumePolicy
    reason: str


def _existing_processing_run_statuses(
    *names: str,
) -> frozenset[ProcessingRunStatus]:
    return frozenset(
        member
        for name in names
        if isinstance(
            member := getattr(ProcessingRunStatus, name, None),
            ProcessingRunStatus,
        )
    )


def _existing_document_statuses(
    *names: str,
) -> frozenset[KnowledgeDocumentStatus]:
    return frozenset(
        member
        for name in names
        if isinstance(
            member := getattr(KnowledgeDocumentStatus, name, None),
            KnowledgeDocumentStatus,
        )
    )


CANCELLABLE_PROCESSING_RUN_STATUSES: frozenset[ProcessingRunStatus] = (
    _existing_processing_run_statuses(
        "PENDING",
        "RUNNING",
        "PAUSING",
        "PAUSED_QUOTA",
        "PAUSED_PROVIDER",
        "PAUSED_SERVER_INTERRUPTED",
    )
)

CANCELLABLE_DOCUMENT_STATUSES: frozenset[KnowledgeDocumentStatus] = (
    _existing_document_statuses(
        "UPLOADED",
        "SECTIONED",
        "PROCESSING",
        "PARTIALLY_PROCESSED",
        "PAUSED",
    )
)


def _rejected_cancellation_decision(
    *,
    reason: str,
    existing_run: KnowledgeProcessingRun | None = None,
) -> ProcessingCancellationDecision:
    return ProcessingCancellationDecision(
        may_cancel=False,
        document_status=None,
        processing_run_status=None,
        resume_policy=(
            ResumePolicy.FORBIDDEN
            if existing_run is None
            else resume_policy_for_status(existing_run.status)
        ),
        reason=reason,
    )


def decide_processing_cancellation(
    *,
    document: KnowledgeDocument,
    existing_run: KnowledgeProcessingRun | None,
) -> ProcessingCancellationDecision:
    if document.status is KnowledgeDocumentStatus.DELETED:
        return _rejected_cancellation_decision(
            reason="deleted document cannot be cancelled",
            existing_run=existing_run,
        )

    if existing_run is None:
        return _rejected_cancellation_decision(
            reason="cancellation requires an existing processing run",
        )

    if existing_run.document_id != document.document_id:
        return _rejected_cancellation_decision(
            reason="cancellation requires the same document_id",
            existing_run=existing_run,
        )

    if document.status not in CANCELLABLE_DOCUMENT_STATUSES:
        return _rejected_cancellation_decision(
            reason=f"document cannot be cancelled from status {document.status.value}",
            existing_run=existing_run,
        )

    if existing_run.status not in CANCELLABLE_PROCESSING_RUN_STATUSES:
        return _rejected_cancellation_decision(
            reason=(
                "processing run cannot be cancelled from status "
                f"{existing_run.status.value}"
            ),
            existing_run=existing_run,
        )

    return ProcessingCancellationDecision(
        may_cancel=True,
        document_status=KnowledgeDocumentStatus.CANCELLED,
        processing_run_status=ProcessingRunStatus.CANCELLED_BY_USER,
        resume_policy=ResumePolicy.MANUAL_ONLY,
        reason="explicit user cancellation disables automatic recovery",
    )

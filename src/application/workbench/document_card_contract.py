from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class WorkbenchDocumentLifecycleState(StrEnum):
    UPLOADED = "uploaded"
    SECTIONED = "sectioned"
    PROCESSING = "processing"
    PAUSED_MANUAL = "paused_manual"
    PAUSED_QUOTA = "paused_quota"
    PAUSED_PROVIDER = "paused_provider"
    PAUSED_SERVER_INTERRUPTED = "paused_server_interrupted"
    AUTO_RECOVERY_SCHEDULED = "auto_recovery_scheduled"
    CANCELLED = "cancelled"
    FAILED = "failed"
    READY_FOR_CURATION = "ready_for_curation"
    READY_FOR_PUBLICATION = "ready_for_publication"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    TRANSIENT_PURGED = "transient_purged"
    DELETED = "deleted"


class WorkbenchDocumentRetentionState(StrEnum):
    ACTIVE_PROCESSING = "active_processing"
    READY_FOR_PUBLICATION = "ready_for_publication"
    PUBLISHED_RETAINED = "published_retained"
    TRANSIENT_PURGED = "transient_purged"
    DELETED = "deleted"


class WorkbenchTimerMode(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    PUBLISHED = "published"


class WorkbenchRecoveryMode(StrEnum):
    NONE = "none"
    SCHEDULED_AUTO_RESUME = "scheduled_auto_resume"
    MANUAL_ONLY = "manual_only"
    FORBIDDEN = "forbidden"


class WorkbenchCardActionId(StrEnum):
    CANCEL_PROCESSING = "cancel_processing"
    RESUME_PROCESSING = "resume_processing"
    CANCEL_SCHEDULED_RECOVERY = "cancel_scheduled_recovery"
    DELETE_DOCUMENT = "delete_document"
    OPEN_WORKBENCH = "open_workbench"
    OPEN_CURATION = "open_curation"
    PUBLISH_READY = "publish_ready"
    OPEN_PUBLISHED_SURFACES = "open_published_surfaces"
    REPROCESS_FRESH = "reprocess_fresh"


class WorkbenchCardActionTone(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    WARNING = "warning"
    DANGER = "danger"


class WorkbenchCardMessageSeverity(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class WorkbenchCardReasonCode(StrEnum):
    RUNNING = "running"
    PAUSED_BY_USER = "paused_by_user"
    PAUSED_API_LIMIT = "paused_api_limit"
    PAUSED_PROVIDER = "paused_provider"
    PAUSED_SERVER_INTERRUPTED = "paused_server_interrupted"
    AUTO_RESUME_SCHEDULED = "auto_resume_scheduled"
    MANUAL_RESUME_AVAILABLE = "manual_resume_available"
    RESUME_FORBIDDEN_AFTER_PUBLICATION = "resume_forbidden_after_publication"
    READY_FOR_CURATION = "ready_for_curation"
    READY_FOR_PUBLICATION = "ready_for_publication"
    PUBLISHED_WORKSPACE_CLEANED = "published_workspace_cleaned"
    DOCUMENT_DELETED = "document_deleted"
    PROCESSING_FAILED = "processing_failed"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True, slots=True)
class WorkbenchCardUserMessage:
    code: WorkbenchCardReasonCode
    severity: WorkbenchCardMessageSeverity
    i18n_key: str
    default_message: str
    debug_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.i18n_key.strip():
            raise ValueError("user message i18n_key must not be blank")
        if not self.default_message.strip():
            raise ValueError("user message default_message must not be blank")
        if self.debug_ref is not None and not self.debug_ref.strip():
            raise ValueError("debug_ref must not be blank when provided")


@dataclass(frozen=True, slots=True)
class WorkbenchCardErrorView:
    reason_code: WorkbenchCardReasonCode
    user_message: WorkbenchCardUserMessage
    recoverable: bool
    retry_available: bool
    internal_error_ref: str | None = None

    def __post_init__(self) -> None:
        if self.internal_error_ref is not None and not self.internal_error_ref.strip():
            raise ValueError("internal_error_ref must not be blank when provided")


@dataclass(frozen=True, slots=True)
class WorkbenchCardTimerView:
    mode: WorkbenchTimerMode
    active_elapsed_seconds: int
    wall_elapsed_seconds: int
    current_active_started_at: datetime | None
    i18n_key: str
    default_label: str

    def __post_init__(self) -> None:
        if self.active_elapsed_seconds < 0:
            raise ValueError("active_elapsed_seconds must be non-negative")
        if self.wall_elapsed_seconds < 0:
            raise ValueError("wall_elapsed_seconds must be non-negative")
        if self.wall_elapsed_seconds < self.active_elapsed_seconds:
            raise ValueError(
                "wall_elapsed_seconds must not be below active elapsed time"
            )
        if (
            self.mode is WorkbenchTimerMode.RUNNING
            and self.current_active_started_at is None
        ):
            raise ValueError("running timer requires current_active_started_at")
        if (
            self.mode is not WorkbenchTimerMode.RUNNING
            and self.current_active_started_at is not None
        ):
            raise ValueError(
                "non-running timer must not expose current_active_started_at"
            )
        if not self.i18n_key.strip():
            raise ValueError("timer i18n_key must not be blank")
        if not self.default_label.strip():
            raise ValueError("timer default_label must not be blank")


@dataclass(frozen=True, slots=True)
class WorkbenchCardUsageView:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    llm_call_count: int
    i18n_key: str = "knowledge.workbench.card.usage"

    def __post_init__(self) -> None:
        for field_name, value in (
            ("prompt_tokens", self.prompt_tokens),
            ("completion_tokens", self.completion_tokens),
            ("total_tokens", self.total_tokens),
            ("llm_call_count", self.llm_call_count),
        ):
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.total_tokens < self.prompt_tokens + self.completion_tokens:
            raise ValueError("total_tokens must include prompt and completion tokens")
        if not self.i18n_key.strip():
            raise ValueError("usage i18n_key must not be blank")


@dataclass(frozen=True, slots=True)
class WorkbenchSectionSummaryView:
    total: int
    processed: int
    failed: int
    pending: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("total", self.total),
            ("processed", self.processed),
            ("failed", self.failed),
            ("pending", self.pending),
        ):
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.processed + self.failed + self.pending > self.total:
            raise ValueError("section counters exceed total")


@dataclass(frozen=True, slots=True)
class WorkbenchRegistrySummaryView:
    entry_count: int
    final_snapshot_id: str | None
    retained: bool

    def __post_init__(self) -> None:
        if self.entry_count < 0:
            raise ValueError("entry_count must be non-negative")
        if self.retained and not self.final_snapshot_id:
            raise ValueError("retained registry requires final_snapshot_id")


@dataclass(frozen=True, slots=True)
class WorkbenchSurfaceSummaryView:
    draft_count: int
    ready_count: int
    published_count: int
    rejected_count: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("draft_count", self.draft_count),
            ("ready_count", self.ready_count),
            ("published_count", self.published_count),
            ("rejected_count", self.rejected_count),
        ):
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class WorkbenchRuntimeSummaryView:
    publication_id: str | None
    runtime_entry_count: int

    def __post_init__(self) -> None:
        if self.runtime_entry_count < 0:
            raise ValueError("runtime_entry_count must be non-negative")
        if self.runtime_entry_count > 0 and not self.publication_id:
            raise ValueError("runtime entries require publication_id")


@dataclass(frozen=True, slots=True)
class WorkbenchRecoveryView:
    mode: WorkbenchRecoveryMode
    scheduled_at: datetime | None
    can_cancel_scheduled_resume: bool
    reason_code: WorkbenchCardReasonCode
    i18n_key: str
    default_message: str

    def __post_init__(self) -> None:
        if self.mode is WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME:
            if self.scheduled_at is None:
                raise ValueError("scheduled auto-resume requires scheduled_at")
            if not self.can_cancel_scheduled_resume:
                raise ValueError("scheduled auto-resume must be cancellable by user")
        else:
            if self.scheduled_at is not None:
                raise ValueError("non-scheduled recovery must not expose scheduled_at")
            if self.can_cancel_scheduled_resume:
                raise ValueError("only scheduled recovery can be cancelled")
        if not self.i18n_key.strip():
            raise ValueError("recovery i18n_key must not be blank")
        if not self.default_message.strip():
            raise ValueError("recovery default_message must not be blank")


@dataclass(frozen=True, slots=True)
class WorkbenchCardActionView:
    action_id: WorkbenchCardActionId
    visible: bool
    enabled: bool
    tone: WorkbenchCardActionTone
    i18n_key: str
    default_label: str
    reason_code: WorkbenchCardReasonCode | None = None
    confirmation_i18n_key: str | None = None
    default_confirmation: str | None = None

    def __post_init__(self) -> None:
        if not self.i18n_key.strip():
            raise ValueError("action i18n_key must not be blank")
        if not self.default_label.strip():
            raise ValueError("action default_label must not be blank")
        if self.enabled and not self.visible:
            raise ValueError("enabled action must be visible")
        if not self.enabled and self.visible and self.reason_code is None:
            raise ValueError("visible disabled action requires reason_code")
        if (
            self.confirmation_i18n_key is not None
            and not self.confirmation_i18n_key.strip()
        ):
            raise ValueError("confirmation_i18n_key must not be blank")
        if (
            self.default_confirmation is not None
            and not self.default_confirmation.strip()
        ):
            raise ValueError("default_confirmation must not be blank")
        if (self.confirmation_i18n_key is None) != (self.default_confirmation is None):
            raise ValueError(
                "confirmation key and default text must be provided together"
            )


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentCardView:
    document_id: str
    project_id: str
    file_name: str
    source_type: str
    lifecycle_state: WorkbenchDocumentLifecycleState
    retention_state: WorkbenchDocumentRetentionState
    transient_purged: bool
    resume_available: bool
    status_i18n_key: str
    default_status_label: str
    status_description_i18n_key: str
    default_status_description: str
    timer: WorkbenchCardTimerView
    usage: WorkbenchCardUsageView
    sections: WorkbenchSectionSummaryView
    registry: WorkbenchRegistrySummaryView
    surfaces: WorkbenchSurfaceSummaryView
    runtime: WorkbenchRuntimeSummaryView
    recovery: WorkbenchRecoveryView
    actions: tuple[WorkbenchCardActionView, ...]
    messages: tuple[WorkbenchCardUserMessage, ...] = ()
    error: WorkbenchCardErrorView | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name, value in (
            ("document_id", self.document_id),
            ("project_id", self.project_id),
            ("file_name", self.file_name),
            ("source_type", self.source_type),
            ("status_i18n_key", self.status_i18n_key),
            ("default_status_label", self.default_status_label),
            ("status_description_i18n_key", self.status_description_i18n_key),
            ("default_status_description", self.default_status_description),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")

        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("document card actions must be unique")

        if self.transient_purged:
            if (
                self.retention_state
                is not WorkbenchDocumentRetentionState.TRANSIENT_PURGED
            ):
                raise ValueError(
                    "transient_purged card requires transient_purged retention state"
                )
            if self.resume_available:
                raise ValueError("resume must be unavailable after transient purge")
            resume_action = self.action(WorkbenchCardActionId.RESUME_PROCESSING)
            if resume_action is not None and resume_action.enabled:
                raise ValueError(
                    "resume action must not be enabled after transient purge"
                )

        if (
            self.lifecycle_state
            is WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED
        ):
            cancel_recovery = self.action(
                WorkbenchCardActionId.CANCEL_SCHEDULED_RECOVERY
            )
            if (
                cancel_recovery is None
                or not cancel_recovery.visible
                or not cancel_recovery.enabled
            ):
                raise ValueError(
                    "auto-recovery card requires enabled cancel scheduled recovery action"
                )

        if self.lifecycle_state in {
            WorkbenchDocumentLifecycleState.READY_FOR_CURATION,
            WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION,
        }:
            open_curation = self.action(WorkbenchCardActionId.OPEN_CURATION)
            if open_curation is None or not open_curation.visible:
                raise ValueError(
                    "curatable document requires visible open curation action"
                )

        if self.error is not None and not any(
            message.severity is WorkbenchCardMessageSeverity.ERROR
            for message in self.messages
        ):
            raise ValueError("error card requires an error user message")

    def action(
        self, action_id: WorkbenchCardActionId
    ) -> WorkbenchCardActionView | None:
        for action in self.actions:
            if action.action_id is action_id:
                return action
        return None

    @property
    def visible_actions(self) -> tuple[WorkbenchCardActionView, ...]:
        return tuple(action for action in self.actions if action.visible)

    @property
    def primary_actions(self) -> tuple[WorkbenchCardActionView, ...]:
        return tuple(
            action
            for action in self.actions
            if action.visible
            and action.enabled
            and action.tone is WorkbenchCardActionTone.PRIMARY
        )


__all__ = [
    "WorkbenchCardActionId",
    "WorkbenchCardActionTone",
    "WorkbenchCardActionView",
    "WorkbenchCardErrorView",
    "WorkbenchCardMessageSeverity",
    "WorkbenchCardReasonCode",
    "WorkbenchCardTimerView",
    "WorkbenchCardUsageView",
    "WorkbenchCardUserMessage",
    "WorkbenchDocumentCardView",
    "WorkbenchDocumentLifecycleState",
    "WorkbenchDocumentRetentionState",
    "WorkbenchRecoveryMode",
    "WorkbenchRecoveryView",
    "WorkbenchRegistrySummaryView",
    "WorkbenchRuntimeSummaryView",
    "WorkbenchSectionSummaryView",
    "WorkbenchSurfaceSummaryView",
    "WorkbenchTimerMode",
]

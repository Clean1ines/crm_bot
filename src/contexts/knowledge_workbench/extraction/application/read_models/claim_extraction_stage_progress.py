from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


class ClaimExtractionStageProgressStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_QUOTA = "waiting_for_quota"
    WAITING = "waiting"
    USER_ACTION_REQUIRED = "user_action_required"
    COMPLETED = "completed"
    FAILED = "failed"
    REQUIRES_USER_CHOICE = "requires_user_choice"
    CANCELLED = "cancelled"
    PARTIAL_CANCELLED = "partial_cancelled"


class ClaimExtractionStageBlockerKind(StrEnum):
    ACTIVE_LEASE = "active_lease"
    QUOTA_WAIT = "quota_wait"
    RETRY_WAIT = "retry_wait"
    USER_ACTION_REQUIRED = "user_action_required"
    SPLIT_REQUIRED = "split_required"
    TERMINAL_FAILED = "terminal_failed"
    CANCELLED = "cancelled"


class ClaimExtractionStageBlockerReason(StrEnum):
    WAITING_FOR_MINUTE_QUOTA = "waiting_for_minute_quota"
    WAITING_FOR_DAILY_RESET = "waiting_for_daily_reset"
    PROVIDER_RETRY_SCHEDULED = "provider_retry_scheduled"
    NETWORK_RETRY_SCHEDULED = "network_retry_scheduled"
    INVALID_OUTPUT_RETRY_SCHEDULED = "invalid_output_retry_scheduled"
    VALIDATION_RETRY_SCHEDULED = "validation_retry_scheduled"
    EMPTY_OUTPUT_RETRY_SCHEDULED = "empty_output_retry_scheduled"
    SOURCE_UNIT_SPLIT_REQUIRED = "source_unit_split_required"
    DAILY_LIMIT_REQUIRES_USER_CHOICE = "daily_limit_requires_user_choice"
    TERMINAL_FAILURE = "terminal_failure"
    CANCELLED = "cancelled"


class ClaimExtractionStageNextAction(StrEnum):
    WAIT_FOR_ACTIVE_LEASE = "wait_for_active_lease"
    RESUME_AFTER_WAIT = "resume_after_wait"
    RETRY_WHEN_DUE = "retry_when_due"
    SPLIT_WORK_PAYLOAD = "split_work_payload"
    CHOOSE_DAILY_LIMIT_RECOVERY = "choose_daily_limit_recovery"
    INSPECT_TERMINAL_FAILURE = "inspect_terminal_failure"
    STOPPED_CANCELLED = "stopped_cancelled"


class ClaimExtractionStageProgressQueryPort(Protocol):
    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]: ...

    def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageProgressQuery:
    workflow_run_id: str
    stage_run_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageProgress:
    status: ClaimExtractionStageProgressStatus
    ready_count: int
    leased_count: int
    deferred_count: int
    completed_count: int
    retryable_failed_count: int
    terminal_failed_count: int
    cancelled_count: int
    split_superseded_count: int
    artifacts_count: int
    nearest_wait_until: datetime | None
    blocker_kind: ClaimExtractionStageBlockerKind | None
    blocker_reason: ClaimExtractionStageBlockerReason | None
    next_action: ClaimExtractionStageNextAction | None
    user_action_required_count: int

    @property
    def total_work_item_count(self) -> int:
        return (
            self.ready_count
            + self.leased_count
            + self.deferred_count
            + self.completed_count
            + self.retryable_failed_count
            + self.terminal_failed_count
            + self.cancelled_count
            + self.split_superseded_count
            + self.user_action_required_count
        )

    @property
    def resume_after(self) -> datetime | None:
        return self.nearest_wait_until


@dataclass(frozen=True, slots=True)
class _StageBlockerInterpretation:
    kind: ClaimExtractionStageBlockerKind | None
    reason: ClaimExtractionStageBlockerReason | None
    next_action: ClaimExtractionStageNextAction | None


class ClaimExtractionStageProgressReadModel:
    def __init__(self, *, query_port: ClaimExtractionStageProgressQueryPort) -> None:
        self._query_port = query_port

    def execute(
        self,
        query: ClaimExtractionStageProgressQuery,
    ) -> ClaimExtractionStageProgress:
        work_items = self._query_port.load_work_items(
            workflow_run_id=query.workflow_run_id,
            stage_run_id=query.stage_run_id,
        )
        artifacts_count = self._query_port.count_artifacts(
            workflow_run_id=query.workflow_run_id,
            stage_run_id=query.stage_run_id,
        )
        if artifacts_count < 0:
            raise ValueError("artifacts_count must be >= 0")

        ready_count = _count_status(work_items, WorkItemStatus.READY)
        leased_count = _count_status(work_items, WorkItemStatus.LEASED)
        deferred_count = _count_status(work_items, WorkItemStatus.DEFERRED)
        completed_count = _count_status(work_items, WorkItemStatus.COMPLETED)
        retryable_failed_count = _count_status(
            work_items,
            WorkItemStatus.RETRYABLE_FAILED,
        )
        terminal_failed_count = _count_status(
            work_items,
            WorkItemStatus.TERMINAL_FAILED,
        )
        cancelled_count = _count_status(work_items, WorkItemStatus.CANCELLED)
        split_superseded_count = _count_status(
            work_items,
            WorkItemStatus.SPLIT_SUPERSEDED,
        )
        user_action_required_count = _count_status(
            work_items,
            WorkItemStatus.USER_ACTION_REQUIRED,
        )
        nearest_wait_until = _nearest_wait_until(work_items)
        total_count = len(work_items)
        blocker = _stage_blocker_interpretation(work_items)

        return ClaimExtractionStageProgress(
            status=_progress_status(
                total_count=total_count,
                ready_count=ready_count,
                leased_count=leased_count,
                deferred_count=deferred_count,
                completed_count=completed_count,
                retryable_failed_count=retryable_failed_count,
                terminal_failed_count=terminal_failed_count,
                cancelled_count=cancelled_count,
                split_superseded_count=split_superseded_count,
                user_action_required_count=user_action_required_count,
            ),
            ready_count=ready_count,
            leased_count=leased_count,
            deferred_count=deferred_count,
            completed_count=completed_count,
            retryable_failed_count=retryable_failed_count,
            terminal_failed_count=terminal_failed_count,
            cancelled_count=cancelled_count,
            split_superseded_count=split_superseded_count,
            artifacts_count=artifacts_count,
            nearest_wait_until=nearest_wait_until,
            blocker_kind=blocker.kind,
            blocker_reason=blocker.reason,
            next_action=blocker.next_action,
            user_action_required_count=user_action_required_count,
        )


def _count_status(work_items: tuple[WorkItem, ...], status: WorkItemStatus) -> int:
    return sum(1 for item in work_items if item.status is status)


def _nearest_wait_until(work_items: tuple[WorkItem, ...]) -> datetime | None:
    waits = tuple(
        item.next_attempt_at.value
        for item in work_items
        if item.status
        in {
            WorkItemStatus.DEFERRED,
            WorkItemStatus.RETRYABLE_FAILED,
        }
        and item.next_attempt_at is not None
    )
    if not waits:
        return None
    return min(waits)


def _progress_status(
    *,
    total_count: int,
    ready_count: int,
    leased_count: int,
    deferred_count: int,
    completed_count: int,
    retryable_failed_count: int,
    terminal_failed_count: int,
    cancelled_count: int,
    split_superseded_count: int,
    user_action_required_count: int,
) -> ClaimExtractionStageProgressStatus:
    if total_count == 0:
        return ClaimExtractionStageProgressStatus.PENDING

    if terminal_failed_count > 0:
        return ClaimExtractionStageProgressStatus.FAILED

    if user_action_required_count > 0:
        return ClaimExtractionStageProgressStatus.USER_ACTION_REQUIRED

    if leased_count > 0:
        return ClaimExtractionStageProgressStatus.IN_PROGRESS

    if cancelled_count == total_count:
        return ClaimExtractionStageProgressStatus.CANCELLED

    if cancelled_count > 0:
        return ClaimExtractionStageProgressStatus.PARTIAL_CANCELLED

    completed_total = completed_count + split_superseded_count
    if completed_total == total_count:
        return ClaimExtractionStageProgressStatus.COMPLETED

    if deferred_count > 0 or retryable_failed_count > 0:
        return ClaimExtractionStageProgressStatus.WAITING

    if ready_count > 0:
        return ClaimExtractionStageProgressStatus.PENDING

    return ClaimExtractionStageProgressStatus.WAITING


def _stage_blocker_interpretation(
    work_items: tuple[WorkItem, ...],
) -> _StageBlockerInterpretation:
    if _has_status(work_items, WorkItemStatus.TERMINAL_FAILED):
        return _StageBlockerInterpretation(
            kind=ClaimExtractionStageBlockerKind.TERMINAL_FAILED,
            reason=ClaimExtractionStageBlockerReason.TERMINAL_FAILURE,
            next_action=ClaimExtractionStageNextAction.INSPECT_TERMINAL_FAILURE,
        )

    user_action_item = _first_with_status(
        work_items,
        WorkItemStatus.USER_ACTION_REQUIRED,
    )
    if user_action_item is not None:
        return _user_action_required_interpretation(user_action_item)

    if _has_status(work_items, WorkItemStatus.LEASED):
        return _StageBlockerInterpretation(
            kind=ClaimExtractionStageBlockerKind.ACTIVE_LEASE,
            reason=None,
            next_action=ClaimExtractionStageNextAction.WAIT_FOR_ACTIVE_LEASE,
        )

    waiting_item = _first_waiting_item(work_items)
    if waiting_item is not None:
        return _waiting_interpretation(waiting_item)

    if _has_status(work_items, WorkItemStatus.CANCELLED):
        return _StageBlockerInterpretation(
            kind=ClaimExtractionStageBlockerKind.CANCELLED,
            reason=ClaimExtractionStageBlockerReason.CANCELLED,
            next_action=ClaimExtractionStageNextAction.STOPPED_CANCELLED,
        )

    return _StageBlockerInterpretation(kind=None, reason=None, next_action=None)


def _has_status(work_items: tuple[WorkItem, ...], status: WorkItemStatus) -> bool:
    return any(item.status is status for item in work_items)


def _first_with_status(
    work_items: tuple[WorkItem, ...],
    status: WorkItemStatus,
) -> WorkItem | None:
    return next((item for item in work_items if item.status is status), None)


def _first_waiting_item(work_items: tuple[WorkItem, ...]) -> WorkItem | None:
    waiting_items = tuple(
        item
        for item in work_items
        if item.status
        in {
            WorkItemStatus.DEFERRED,
            WorkItemStatus.RETRYABLE_FAILED,
        }
    )
    if not waiting_items:
        return None

    return min(
        waiting_items,
        key=lambda item: (
            item.next_attempt_at.value
            if item.next_attempt_at is not None
            else datetime.max
        ),
    )


def _user_action_required_interpretation(
    item: WorkItem,
) -> _StageBlockerInterpretation:
    error_kind = _llm_error_kind(item.last_error_kind)

    if error_kind is LlmErrorKind.DAILY_LIMIT:
        return _StageBlockerInterpretation(
            kind=ClaimExtractionStageBlockerKind.USER_ACTION_REQUIRED,
            reason=ClaimExtractionStageBlockerReason.DAILY_LIMIT_REQUIRES_USER_CHOICE,
            next_action=ClaimExtractionStageNextAction.CHOOSE_DAILY_LIMIT_RECOVERY,
        )

    return _StageBlockerInterpretation(
        kind=ClaimExtractionStageBlockerKind.USER_ACTION_REQUIRED,
        reason=ClaimExtractionStageBlockerReason.TERMINAL_FAILURE,
        next_action=ClaimExtractionStageNextAction.INSPECT_TERMINAL_FAILURE,
    )


def _waiting_interpretation(item: WorkItem) -> _StageBlockerInterpretation:
    error_kind = _llm_error_kind(item.last_error_kind)
    if error_kind is LlmErrorKind.MINUTE_LIMIT:
        return _StageBlockerInterpretation(
            kind=ClaimExtractionStageBlockerKind.QUOTA_WAIT,
            reason=ClaimExtractionStageBlockerReason.WAITING_FOR_MINUTE_QUOTA,
            next_action=ClaimExtractionStageNextAction.RESUME_AFTER_WAIT,
        )
    if error_kind is LlmErrorKind.DAILY_LIMIT:
        return _StageBlockerInterpretation(
            kind=ClaimExtractionStageBlockerKind.QUOTA_WAIT,
            reason=ClaimExtractionStageBlockerReason.WAITING_FOR_DAILY_RESET,
            next_action=ClaimExtractionStageNextAction.RESUME_AFTER_WAIT,
        )
    if error_kind is LlmErrorKind.REQUEST_TOO_LARGE:
        return _split_required_interpretation()
    if error_kind is LlmErrorKind.OUTPUT_TOO_LARGE:
        return _split_required_interpretation()
    if error_kind is LlmErrorKind.NETWORK_ERROR:
        return _retry_wait_interpretation(
            ClaimExtractionStageBlockerReason.NETWORK_RETRY_SCHEDULED,
        )
    if error_kind is LlmErrorKind.INVALID_OUTPUT:
        return _retry_wait_interpretation(
            ClaimExtractionStageBlockerReason.INVALID_OUTPUT_RETRY_SCHEDULED,
        )
    if error_kind is LlmErrorKind.VALIDATION_FAILED:
        return _retry_wait_interpretation(
            ClaimExtractionStageBlockerReason.VALIDATION_RETRY_SCHEDULED,
        )
    if error_kind is LlmErrorKind.EMPTY_OUTPUT:
        return _retry_wait_interpretation(
            ClaimExtractionStageBlockerReason.EMPTY_OUTPUT_RETRY_SCHEDULED,
        )

    return _retry_wait_interpretation(
        ClaimExtractionStageBlockerReason.PROVIDER_RETRY_SCHEDULED,
    )


def _split_required_interpretation() -> _StageBlockerInterpretation:
    return _StageBlockerInterpretation(
        kind=ClaimExtractionStageBlockerKind.SPLIT_REQUIRED,
        reason=ClaimExtractionStageBlockerReason.SOURCE_UNIT_SPLIT_REQUIRED,
        next_action=ClaimExtractionStageNextAction.SPLIT_WORK_PAYLOAD,
    )


def _retry_wait_interpretation(
    reason: ClaimExtractionStageBlockerReason,
) -> _StageBlockerInterpretation:
    return _StageBlockerInterpretation(
        kind=ClaimExtractionStageBlockerKind.RETRY_WAIT,
        reason=reason,
        next_action=ClaimExtractionStageNextAction.RETRY_WHEN_DUE,
    )


def _llm_error_kind(value: str | None) -> LlmErrorKind:
    if value is None:
        return LlmErrorKind.UNKNOWN
    try:
        return LlmErrorKind(value)
    except ValueError:
        return LlmErrorKind.UNKNOWN


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")

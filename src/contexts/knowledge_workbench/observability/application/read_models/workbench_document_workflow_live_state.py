from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


JsonDict = dict[str, object]


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowTimerLiveView:
    mode: str
    active_elapsed_seconds: int
    wall_elapsed_seconds: int
    current_active_started_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    is_live: bool

    def to_dict(self) -> JsonDict:
        return {
            "mode": self.mode,
            "active_elapsed_seconds": self.active_elapsed_seconds,
            "wall_elapsed_seconds": self.wall_elapsed_seconds,
            "current_active_started_at": _dt(self.current_active_started_at),
            "started_at": _dt(self.started_at),
            "completed_at": _dt(self.completed_at),
            "is_live": self.is_live,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowUsageLiveView:
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_llm_calls: int
    model_summaries: tuple["WorkbenchWorkflowModelUsageLiveView", ...]

    def to_dict(self) -> JsonDict:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_llm_calls": self.total_llm_calls,
            "model_summaries": [item.to_dict() for item in self.model_summaries],
        }


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowModelUsageLiveView:
    model_provider: str | None
    model_name: str | None
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms_total: int

    def to_dict(self) -> JsonDict:
        return {
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "call_count": self.call_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms_total": self.duration_ms_total,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowStageLiveView:
    id: str
    label: str
    status: str
    current: int
    total: int
    message: str
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "started_at": _dt(self.started_at),
            "completed_at": _dt(self.completed_at),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowTimelineEntryLiveView:
    timeline_entry_id: str
    event_type: str
    phase: str
    severity: str
    message: str
    occurred_at: datetime
    source_ref: str | None
    work_item_id: str | None
    attempt_id: str | None

    def to_dict(self) -> JsonDict:
        return {
            "timeline_entry_id": self.timeline_entry_id,
            "event_type": self.event_type,
            "phase": self.phase,
            "severity": self.severity,
            "message": self.message,
            "occurred_at": _dt(self.occurred_at),
            "source_ref": self.source_ref,
            "work_item_id": self.work_item_id,
            "attempt_id": self.attempt_id,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchRetryTimerLiveView:
    retry_available_at: datetime | None
    seconds_until_retry: int | None

    def to_dict(self) -> JsonDict:
        return {
            "retry_available_at": _dt(self.retry_available_at),
            "seconds_until_retry": self.seconds_until_retry,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchSectionQueueItemLiveView:
    queue_item_id: str
    section_id: str
    section_index: int
    section_key: str
    status: str
    attempt_count: int
    lease_expires_at: datetime | None
    next_attempt_at: datetime | None
    claimed_by_worker_id: str | None
    error_kind: str | None
    retry_plan: str | None
    user_action_required: bool
    blocked_reason: str | None
    retry_timer: WorkbenchRetryTimerLiveView

    def to_dict(self) -> JsonDict:
        return {
            "queue_item_id": self.queue_item_id,
            "section_id": self.section_id,
            "section_index": self.section_index,
            "section_key": self.section_key,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "lease_expires_at": _dt(self.lease_expires_at),
            "next_attempt_at": _dt(self.next_attempt_at),
            "claimed_by_worker_id": self.claimed_by_worker_id,
            "error_kind": self.error_kind,
            "retry_plan": self.retry_plan,
            "user_action_required": self.user_action_required,
            "blocked_reason": self.blocked_reason,
            "retry_timer": self.retry_timer.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class WorkbenchSectionLaneLiveView:
    lane_index: int
    lane_id: str
    ready_count: int
    leased_count: int
    done_count: int
    failed_count: int
    waiting_count: int
    total_attempt_count: int
    max_attempt_count: int
    items: tuple[WorkbenchSectionQueueItemLiveView, ...]

    def to_dict(self) -> JsonDict:
        return {
            "lane_index": self.lane_index,
            "lane_id": self.lane_id,
            "ready_count": self.ready_count,
            "leased_count": self.leased_count,
            "done_count": self.done_count,
            "failed_count": self.failed_count,
            "waiting_count": self.waiting_count,
            "total_attempt_count": self.total_attempt_count,
            "max_attempt_count": self.max_attempt_count,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True, slots=True)
class WorkbenchLlmAttemptLiveView:
    node_run_id: str
    section_id: str | None
    node_name: str
    node_kind: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    model_provider: str | None
    model_name: str | None
    account_ref: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    remaining_minute_requests: int | None
    remaining_minute_tokens: int | None
    minute_reset_at: datetime | None
    remaining_daily_requests: int | None
    remaining_daily_tokens: int | None
    daily_reset_at: datetime | None
    error_kind: str | None
    error_message_user: str | None
    next_attempt_at: datetime | None
    retry_plan: str | None
    user_action_required: bool
    blocked_reason: str | None

    def to_dict(self) -> JsonDict:
        return {
            "node_run_id": self.node_run_id,
            "section_id": self.section_id,
            "node_name": self.node_name,
            "node_kind": self.node_kind,
            "status": self.status,
            "started_at": _dt(self.started_at),
            "completed_at": _dt(self.completed_at),
            "duration_ms": self.duration_ms,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "account_ref": self.account_ref,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "remaining_minute_requests": self.remaining_minute_requests,
            "remaining_minute_tokens": self.remaining_minute_tokens,
            "minute_reset_at": _dt(self.minute_reset_at),
            "remaining_daily_requests": self.remaining_daily_requests,
            "remaining_daily_tokens": self.remaining_daily_tokens,
            "daily_reset_at": _dt(self.daily_reset_at),
            "error_kind": self.error_kind,
            "error_message_user": self.error_message_user,
            "next_attempt_at": _dt(self.next_attempt_at),
            "retry_plan": self.retry_plan,
            "user_action_required": self.user_action_required,
            "blocked_reason": self.blocked_reason,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchCurationAvailabilityView:
    available: bool
    reason_code: str
    workflow_run_id: str | None
    workspace_ref: str | None
    workspace_status: str | None
    item_count: int
    excluded_item_count: int

    def to_dict(self) -> JsonDict:
        return {
            "available": self.available,
            "reason_code": self.reason_code,
            "workflow_run_id": self.workflow_run_id,
            "workspace_ref": self.workspace_ref,
            "workspace_status": self.workspace_status,
            "item_count": self.item_count,
            "excluded_item_count": self.excluded_item_count,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowActionView:
    action_id: str
    visible: bool
    enabled: bool
    reason_code: str | None

    def to_dict(self) -> JsonDict:
        return {
            "action_id": self.action_id,
            "visible": self.visible,
            "enabled": self.enabled,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchWorkflowLiveState:
    workflow_run_id: str | None
    source_document_ref: str | None
    workflow_status: str | None
    current_phase: str | None
    timer: WorkbenchWorkflowTimerLiveView
    usage: WorkbenchWorkflowUsageLiveView
    stages: tuple[WorkbenchWorkflowStageLiveView, ...]
    section_lanes: tuple[WorkbenchSectionLaneLiveView, ...]
    llm_attempts: tuple[WorkbenchLlmAttemptLiveView, ...]
    timeline: tuple[WorkbenchWorkflowTimelineEntryLiveView, ...]
    curation: WorkbenchCurationAvailabilityView
    actions: tuple[WorkbenchWorkflowActionView, ...]

    def to_dict(self) -> JsonDict:
        return {
            "workflow_run_id": self.workflow_run_id,
            "source_document_ref": self.source_document_ref,
            "workflow_status": self.workflow_status,
            "current_phase": self.current_phase,
            "timer": self.timer.to_dict(),
            "usage": self.usage.to_dict(),
            "stages": [stage.to_dict() for stage in self.stages],
            "section_lanes": [lane.to_dict() for lane in self.section_lanes],
            "llm_attempts": [attempt.to_dict() for attempt in self.llm_attempts],
            "timeline": [entry.to_dict() for entry in self.timeline],
            "curation": self.curation.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentWorkflowLiveState:
    document_id: str
    project_id: str
    file_name: str
    document_status: str
    current_processing_run_id: str | None
    workflow: WorkbenchWorkflowLiveState

    def to_dict(self) -> JsonDict:
        return {
            "document_id": self.document_id,
            "project_id": self.project_id,
            "file_name": self.file_name,
            "document_status": self.document_status,
            "current_processing_run_id": self.current_processing_run_id,
            "workflow": self.workflow.to_dict(),
        }

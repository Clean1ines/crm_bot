from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionFrontendEventSummary,
    CapacityWindowAdmissionPassResult,
    CapacityWindowAdmissionSkippedReason,
)


class CapacityAdmissionPhaseMappingDecision(StrEnum):
    DISPATCH_PREPARED = "dispatch_prepared"
    CAPACITY_WAITING = "capacity_waiting"
    NO_FITTING_WORK_ITEM = "no_fitting_work_item"
    ACTIVE_LEASED_WAIT = "active_leased_wait"
    SOURCE_SPLIT_REQUIRED = "source_split_required"
    USER_MODEL_CHOICE_REQUIRED = "user_model_choice_required"
    PROJECTION_CONFLICT = "projection_conflict"
    EXECUTION_LEASE_LOST = "execution_lease_lost"


class CapacityAdmissionPhaseMappingLogEvent(StrEnum):
    PHASE_MAPPING_STARTED = "capacity_admission_phase_mapping_started"
    PHASE_MAPPING_COMPLETED = "capacity_admission_phase_mapping_completed"
    PHASE_MAPPING_SKIPPED = "capacity_admission_phase_mapping_skipped"


@dataclass(frozen=True, slots=True)
class CapacityAdmissionPhaseMappingProfile:
    """Workbench phase profile layered above generic capacity admission.

    This profile is intentionally phase-specific but payload-agnostic. It binds
    a generic admission result to workflow event/command names without letting
    Capacity Admission know claim-builder or compaction business semantics.
    """

    phase: str
    operation_key: str
    work_kind: str
    dispatch_prepared_event_type: str
    execute_command_type: str
    supports_source_split_required: bool
    supports_user_model_choice_required: bool
    requires_frontend_projection: bool = True

    def __post_init__(self) -> None:
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.operation_key, "operation_key")
        _require_non_empty_text(self.work_kind, "work_kind")
        _require_non_empty_text(
            self.dispatch_prepared_event_type,
            "dispatch_prepared_event_type",
        )
        _require_non_empty_text(self.execute_command_type, "execute_command_type")
        if not isinstance(self.supports_source_split_required, bool):
            raise TypeError("supports_source_split_required must be bool")
        if not isinstance(self.supports_user_model_choice_required, bool):
            raise TypeError("supports_user_model_choice_required must be bool")
        if not isinstance(self.requires_frontend_projection, bool):
            raise TypeError("requires_frontend_projection must be bool")


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_empty_text_tuple(
    value: tuple[str, ...],
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        _require_non_empty_text(item, field_name)


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


CLAIM_BUILDER_ADMISSION_PHASE_PROFILE = CapacityAdmissionPhaseMappingProfile(
    phase="CLAIM_BUILDER_SECTION_EXTRACTION",
    operation_key="prepare_claim_builder_dispatch",
    work_kind="knowledge_workbench.claim_builder.section_extraction",
    dispatch_prepared_event_type="ClaimBuilderDispatchBatchPrepared",
    execute_command_type="ExecuteClaimBuilderSection",
    supports_source_split_required=True,
    supports_user_model_choice_required=False,
)


DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE = CapacityAdmissionPhaseMappingProfile(
    phase="DRAFT_CLAIM_COMPACTION",
    operation_key="prepare_draft_claim_compaction_dispatch",
    work_kind="knowledge_workbench.draft_claim_compaction",
    dispatch_prepared_event_type="DraftClaimCompactionDispatchBatchPrepared",
    execute_command_type="ExecuteDraftClaimCompaction",
    supports_source_split_required=False,
    supports_user_model_choice_required=True,
)


@dataclass(frozen=True, slots=True)
class CapacityAdmissionPhaseWorkflowEventSummary:
    event_type: str
    event_id: str
    workflow_run_id: str
    work_item_ids: tuple[str, ...] = ()
    attempt_ids: tuple[str, ...] = ()
    projection_event_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.event_type, "event_type")
        _require_non_empty_text(self.event_id, "event_id")
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text_tuple(
            self.work_item_ids,
            "work_item_ids",
            allow_empty=True,
        )
        _require_non_empty_text_tuple(
            self.attempt_ids,
            "attempt_ids",
            allow_empty=True,
        )
        for event_id in self.projection_event_ids:
            if not isinstance(event_id, UUID):
                raise TypeError("projection_event_ids must contain UUID values")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionPhaseExecuteCommandSummary:
    command_type: str
    command_ref: str
    workflow_run_id: str
    work_item_id: str
    attempt_id: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.command_type, "command_type")
        _require_non_empty_text(self.command_ref, "command_ref")
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.attempt_id, "attempt_id")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionPhaseProgressSummary:
    workflow_run_id: str
    phase: str
    operation_key: str
    prepared_dispatch_count: int
    appended_event_count: int
    appended_next_command_count: int
    skipped_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.operation_key, "operation_key")
        _require_non_negative_int(
            self.prepared_dispatch_count,
            "prepared_dispatch_count",
        )
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if self.skipped_reason is not None:
            _require_non_empty_text(self.skipped_reason, "skipped_reason")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionPhaseMappingPlan:
    profile: CapacityAdmissionPhaseMappingProfile
    admission_result: CapacityWindowAdmissionPassResult
    decision: CapacityAdmissionPhaseMappingDecision
    workflow_events: tuple[CapacityAdmissionPhaseWorkflowEventSummary, ...] = ()
    execute_commands: tuple[CapacityAdmissionPhaseExecuteCommandSummary, ...] = ()
    frontend_events: tuple[CapacityAdmissionFrontendEventSummary, ...] = ()
    progress_summary: CapacityAdmissionPhaseProgressSummary | None = None
    occurred_at: datetime | None = None
    log_event: CapacityAdmissionPhaseMappingLogEvent = (
        CapacityAdmissionPhaseMappingLogEvent.PHASE_MAPPING_COMPLETED
    )

    def __post_init__(self) -> None:
        if not isinstance(self.profile, CapacityAdmissionPhaseMappingProfile):
            raise TypeError("profile must be CapacityAdmissionPhaseMappingProfile")
        if not isinstance(self.admission_result, CapacityWindowAdmissionPassResult):
            raise TypeError(
                "admission_result must be CapacityWindowAdmissionPassResult"
            )
        if not isinstance(self.decision, CapacityAdmissionPhaseMappingDecision):
            raise TypeError("decision must be CapacityAdmissionPhaseMappingDecision")
        if not isinstance(self.log_event, CapacityAdmissionPhaseMappingLogEvent):
            raise TypeError("log_event must be CapacityAdmissionPhaseMappingLogEvent")

        self._validate_profile_matches_admission_result()
        self._validate_decision_supported_by_profile()
        self._validate_collections()
        self._validate_decision_shape()

        if self.progress_summary is not None:
            if not isinstance(
                self.progress_summary,
                CapacityAdmissionPhaseProgressSummary,
            ):
                raise TypeError(
                    "progress_summary must be CapacityAdmissionPhaseProgressSummary"
                )
            if (
                self.progress_summary.workflow_run_id
                != self.admission_result.workflow_run_id
            ):
                raise ValueError("progress_summary workflow_run_id must match result")
            if self.progress_summary.phase != self.profile.phase:
                raise ValueError("progress_summary phase must match profile")
            if self.progress_summary.operation_key != self.profile.operation_key:
                raise ValueError("progress_summary operation_key must match profile")

        if self.occurred_at is not None:
            _require_timezone_aware(self.occurred_at, "occurred_at")

    @property
    def prepared_dispatch_count(self) -> int:
        return len(self.admission_result.started_attempts)

    @property
    def appended_next_command_count(self) -> int:
        return len(self.execute_commands)

    def _validate_profile_matches_admission_result(self) -> None:
        if self.profile.phase != self.admission_result.phase:
            raise ValueError("profile phase must match admission_result phase")
        if self.profile.operation_key != self.admission_result.operation_key:
            raise ValueError(
                "profile operation_key must match admission_result operation_key"
            )
        if self.profile.work_kind != self.admission_result.work_kind:
            raise ValueError("profile work_kind must match admission_result work_kind")

    def _validate_decision_supported_by_profile(self) -> None:
        if (
            self.decision is CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED
            and not self.profile.supports_source_split_required
        ):
            raise ValueError("profile does not support source_split_required decision")
        if (
            self.decision
            is CapacityAdmissionPhaseMappingDecision.USER_MODEL_CHOICE_REQUIRED
            and not self.profile.supports_user_model_choice_required
        ):
            raise ValueError(
                "profile does not support user_model_choice_required decision"
            )

    def _validate_collections(self) -> None:
        for workflow_event in self.workflow_events:
            if not isinstance(
                workflow_event,
                CapacityAdmissionPhaseWorkflowEventSummary,
            ):
                raise TypeError(
                    "workflow_events must contain "
                    "CapacityAdmissionPhaseWorkflowEventSummary"
                )
            if workflow_event.workflow_run_id != self.admission_result.workflow_run_id:
                raise ValueError("workflow event workflow_run_id must match result")

        for execute_command in self.execute_commands:
            if not isinstance(
                execute_command,
                CapacityAdmissionPhaseExecuteCommandSummary,
            ):
                raise TypeError(
                    "execute_commands must contain "
                    "CapacityAdmissionPhaseExecuteCommandSummary"
                )
            if execute_command.workflow_run_id != self.admission_result.workflow_run_id:
                raise ValueError("execute command workflow_run_id must match result")

        for frontend_event in self.frontend_events:
            if not isinstance(frontend_event, CapacityAdmissionFrontendEventSummary):
                raise TypeError(
                    "frontend_events must contain CapacityAdmissionFrontendEventSummary"
                )
            if frontend_event.workflow_run_id != self.admission_result.workflow_run_id:
                raise ValueError("frontend event workflow_run_id must match result")

    def _validate_decision_shape(self) -> None:
        if self.decision is CapacityAdmissionPhaseMappingDecision.DISPATCH_PREPARED:
            if self.admission_result.skipped:
                raise ValueError("dispatch_prepared decision requires admitted result")
            if not self.execute_commands:
                raise ValueError(
                    "dispatch_prepared decision requires execute command summaries"
                )
            return

        if self.decision is CapacityAdmissionPhaseMappingDecision.CAPACITY_WAITING:
            self._require_skipped_reason(
                CapacityWindowAdmissionSkippedReason.CAPACITY_EXHAUSTED
            )
            return

        if self.decision is CapacityAdmissionPhaseMappingDecision.NO_FITTING_WORK_ITEM:
            self._require_skipped_reason(
                CapacityWindowAdmissionSkippedReason.NO_FITTING_WORK_ITEM
            )
            return

        if self.decision is CapacityAdmissionPhaseMappingDecision.ACTIVE_LEASED_WAIT:
            self._require_skipped_reason(
                CapacityWindowAdmissionSkippedReason.ACTIVE_LEASED_WAIT
            )
            return

        if self.decision is CapacityAdmissionPhaseMappingDecision.SOURCE_SPLIT_REQUIRED:
            self._require_skipped_reason(
                CapacityWindowAdmissionSkippedReason.SOURCE_SPLIT_REQUIRED
            )
            return

        if self.decision is CapacityAdmissionPhaseMappingDecision.PROJECTION_CONFLICT:
            self._require_skipped_reason(
                CapacityWindowAdmissionSkippedReason.PROJECTION_CONFLICT
            )
            return

        if self.decision is CapacityAdmissionPhaseMappingDecision.EXECUTION_LEASE_LOST:
            self._require_skipped_reason(
                CapacityWindowAdmissionSkippedReason.EXECUTION_LEASE_LOST
            )
            return

        if (
            self.decision
            is CapacityAdmissionPhaseMappingDecision.USER_MODEL_CHOICE_REQUIRED
        ):
            if not self.admission_result.skipped:
                raise ValueError(
                    "user_model_choice_required decision requires skipped result"
                )
            return

    def _require_skipped_reason(
        self,
        skipped_reason: CapacityWindowAdmissionSkippedReason,
    ) -> None:
        if self.admission_result.skipped_reason is not skipped_reason:
            raise ValueError(
                f"{self.decision.value} decision requires "
                f"{skipped_reason.value} skipped reason"
            )


class CapacityAdmissionPhaseMapperPort(Protocol):
    async def map_admission_result(
        self,
        *,
        admission_result: CapacityWindowAdmissionPassResult,
        profile: CapacityAdmissionPhaseMappingProfile,
        occurred_at: datetime,
    ) -> CapacityAdmissionPhaseMappingPlan:
        """Map generic capacity admission result to Workbench phase side effects."""

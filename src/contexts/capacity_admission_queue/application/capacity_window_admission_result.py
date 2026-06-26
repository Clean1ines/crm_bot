from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class CapacityWindowAdmissionSkippedReason(StrEnum):
    CAPACITY_EXHAUSTED = "capacity_exhausted"
    NO_FITTING_WORK_ITEM = "no_fitting_work_item"
    ACTIVE_LEASED_WAIT = "active_leased_wait"
    SOURCE_SPLIT_REQUIRED = "source_split_required"
    PROJECTION_CONFLICT = "projection_conflict"
    EXECUTION_LEASE_LOST = "execution_lease_lost"


class CapacityWindowAdmissionLogEvent(StrEnum):
    PASS_STARTED = "admission_pass_started"
    PASS_COMPLETED = "admission_pass_completed"
    PASS_SKIPPED = "admission_pass_skipped"
    CANDIDATE_SELECTED = "admission_pass_candidate_selected"
    PROJECTION_CONFLICT = "admission_pass_projection_conflict"
    EXECUTION_LEASE_LOST = "admission_pass_execution_lease_lost"
    ATTEMPT_STARTED = "admission_pass_attempt_started"


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneSummary:
    work_kind: str
    provider: str
    model_ref: str
    account_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_kind, "work_kind")
        _require_non_empty_text(self.provider, "provider")
        _require_non_empty_text(self.model_ref, "model_ref")
        if self.account_ref is not None:
            _require_non_empty_text(self.account_ref, "account_ref")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionSafePreflightSummary:
    decision: str
    reason: str
    active_model_ref: str
    source_split_required: bool = False
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.decision, "decision")
        _require_non_empty_text(self.reason, "reason")
        _require_non_empty_text(self.active_model_ref, "active_model_ref")
        if not isinstance(self.source_split_required, bool):
            raise TypeError("source_split_required must be bool")
        _require_non_empty_text_tuple(
            self.affected_work_item_refs,
            "affected_work_item_refs",
            allow_empty=True,
        )
        _require_non_empty_text_tuple(
            self.source_unit_refs,
            "source_unit_refs",
            allow_empty=True,
        )
        if self.source_split_required and not self.source_unit_refs:
            raise ValueError(
                "source_split_required summary must include source_unit_refs"
            )


@dataclass(frozen=True, slots=True)
class CapacityAdmissionDispatchContextSummary:
    """Safe technical references for workflow/frontend mapping.

    This object deliberately excludes raw schedule payload, source text, prompt text,
    and provider/model output. It may carry only stable technical refs and counts.
    """

    source_ref: str | None = None
    source_unit_ref: str | None = None
    cluster_ref: str | None = None
    subcluster_ref: str | None = None
    group_ref: str | None = None
    batch_ref: str | None = None
    round_index: int | None = None
    expected_output_kind: str | None = None
    input_node_refs: tuple[str, ...] = ()
    input_claim_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_ref", self.source_ref),
            ("source_unit_ref", self.source_unit_ref),
            ("cluster_ref", self.cluster_ref),
            ("subcluster_ref", self.subcluster_ref),
            ("group_ref", self.group_ref),
            ("batch_ref", self.batch_ref),
            ("expected_output_kind", self.expected_output_kind),
        ):
            if value is not None:
                _require_non_empty_text(value, field_name)

        if self.round_index is not None:
            _require_non_negative_int(self.round_index, "round_index")

        _require_non_empty_text_tuple(
            self.input_node_refs,
            "input_node_refs",
            allow_empty=True,
        )
        _require_non_empty_text_tuple(
            self.input_claim_refs,
            "input_claim_refs",
            allow_empty=True,
        )


@dataclass(frozen=True, slots=True)
class CapacityAdmissionAdmittedItemSummary:
    work_item_id: str
    lane: CapacityAdmissionLaneSummary
    selection_kind: str
    input_tokens: int
    artifact_tokens: int
    required_window_tokens: int
    dispatch_context: CapacityAdmissionDispatchContextSummary | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_item_id, "work_item_id")
        if not isinstance(self.lane, CapacityAdmissionLaneSummary):
            raise TypeError("lane must be CapacityAdmissionLaneSummary")
        if self.selection_kind not in {"fresh", "retryable"}:
            raise ValueError("selection_kind must be fresh or retryable")
        _require_positive_int(self.input_tokens, "input_tokens")
        _require_non_negative_int(self.artifact_tokens, "artifact_tokens")
        _require_positive_int(self.required_window_tokens, "required_window_tokens")
        if self.required_window_tokens < self.input_tokens:
            raise ValueError("required_window_tokens must be at least input_tokens")
        if self.dispatch_context is not None and not isinstance(
            self.dispatch_context,
            CapacityAdmissionDispatchContextSummary,
        ):
            raise TypeError(
                "dispatch_context must be CapacityAdmissionDispatchContextSummary"
            )


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionLeaseSummary:
    work_item_id: str
    lane: CapacityAdmissionLaneSummary
    previous_status: str
    status: str
    event_id: UUID

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_item_id, "work_item_id")
        if not isinstance(self.lane, CapacityAdmissionLaneSummary):
            raise TypeError("lane must be CapacityAdmissionLaneSummary")
        if self.previous_status not in {"ready", "retryable_failed"}:
            raise ValueError("previous_status must be ready or retryable_failed")
        if self.status != "leased":
            raise ValueError("status must be leased")
        if not isinstance(self.event_id, UUID):
            raise TypeError("event_id must be UUID")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionCapacityReservationSummary:
    reservation_ref: str
    work_item_id: str
    lane: CapacityAdmissionLaneSummary
    reserved_requests: int
    reserved_tokens: int
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.reservation_ref, "reservation_ref")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        if not isinstance(self.lane, CapacityAdmissionLaneSummary):
            raise TypeError("lane must be CapacityAdmissionLaneSummary")
        _require_positive_int(self.reserved_requests, "reserved_requests")
        _require_positive_int(self.reserved_tokens, "reserved_tokens")
        _require_timezone_aware(self.expires_at, "expires_at")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionStartedAttemptSummary:
    attempt_id: str
    work_item_id: str
    attempt_number: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, "attempt_id")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_positive_int(self.attempt_number, "attempt_number")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionFrontendEventSummary:
    event_kind: str
    workflow_run_id: str
    phase: str
    operation_key: str
    work_kind: str
    lane: CapacityAdmissionLaneSummary
    admitted_count: int
    started_attempt_count: int
    skipped_reason: CapacityWindowAdmissionSkippedReason | None = None
    work_item_ids: tuple[str, ...] = ()
    attempt_ids: tuple[str, ...] = ()
    projection_event_ids: tuple[UUID, ...] = ()
    dispatch_contexts: tuple[CapacityAdmissionDispatchContextSummary, ...] = ()
    occurred_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.event_kind, "event_kind")
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.operation_key, "operation_key")
        _require_non_empty_text(self.work_kind, "work_kind")
        if not isinstance(self.lane, CapacityAdmissionLaneSummary):
            raise TypeError("lane must be CapacityAdmissionLaneSummary")
        _require_non_negative_int(self.admitted_count, "admitted_count")
        _require_non_negative_int(
            self.started_attempt_count,
            "started_attempt_count",
        )
        if self.skipped_reason is not None and not isinstance(
            self.skipped_reason,
            CapacityWindowAdmissionSkippedReason,
        ):
            raise TypeError(
                "skipped_reason must be CapacityWindowAdmissionSkippedReason"
            )
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
        for context in self.dispatch_contexts:
            if not isinstance(context, CapacityAdmissionDispatchContextSummary):
                raise TypeError(
                    "dispatch_contexts must contain "
                    "CapacityAdmissionDispatchContextSummary"
                )
        if self.occurred_at is not None:
            _require_timezone_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionPassResult:
    workflow_run_id: str
    phase: str
    operation_key: str
    work_kind: str
    lane: CapacityAdmissionLaneSummary
    admitted_items: tuple[CapacityAdmissionAdmittedItemSummary, ...] = ()
    projection_leases: tuple[CapacityAdmissionProjectionLeaseSummary, ...] = ()
    capacity_reservations: tuple[CapacityAdmissionCapacityReservationSummary, ...] = ()
    started_attempts: tuple[CapacityAdmissionStartedAttemptSummary, ...] = ()
    appended_execute_command_refs: tuple[str, ...] = ()
    skipped_reason: CapacityWindowAdmissionSkippedReason | None = None
    safe_preflight_summary: CapacityAdmissionSafePreflightSummary | None = None
    frontend_event_summary: CapacityAdmissionFrontendEventSummary | None = None
    log_event: CapacityWindowAdmissionLogEvent = (
        CapacityWindowAdmissionLogEvent.PASS_COMPLETED
    )

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.phase, "phase")
        _require_non_empty_text(self.operation_key, "operation_key")
        _require_non_empty_text(self.work_kind, "work_kind")
        if not isinstance(self.lane, CapacityAdmissionLaneSummary):
            raise TypeError("lane must be CapacityAdmissionLaneSummary")
        if self.lane.work_kind != self.work_kind:
            raise ValueError("lane work_kind must match result work_kind")

        for item in self.admitted_items:
            if not isinstance(item, CapacityAdmissionAdmittedItemSummary):
                raise TypeError(
                    "admitted_items must contain CapacityAdmissionAdmittedItemSummary"
                )
            if item.lane != self.lane:
                raise ValueError("admitted item lane must match result lane")

        for lease in self.projection_leases:
            if not isinstance(lease, CapacityAdmissionProjectionLeaseSummary):
                raise TypeError(
                    "projection_leases must contain "
                    "CapacityAdmissionProjectionLeaseSummary"
                )
            if lease.lane != self.lane:
                raise ValueError("projection lease lane must match result lane")

        for reservation in self.capacity_reservations:
            if not isinstance(
                reservation,
                CapacityAdmissionCapacityReservationSummary,
            ):
                raise TypeError(
                    "capacity_reservations must contain "
                    "CapacityAdmissionCapacityReservationSummary"
                )
            if not _capacity_reservation_lane_matches_result_lane(
                reservation_lane=reservation.lane,
                result_lane=self.lane,
            ):
                raise ValueError("capacity reservation lane must match result lane")

        for attempt in self.started_attempts:
            if not isinstance(attempt, CapacityAdmissionStartedAttemptSummary):
                raise TypeError(
                    "started_attempts must contain "
                    "CapacityAdmissionStartedAttemptSummary"
                )

        _require_non_empty_text_tuple(
            self.appended_execute_command_refs,
            "appended_execute_command_refs",
            allow_empty=True,
        )

        if self.skipped_reason is not None and not isinstance(
            self.skipped_reason,
            CapacityWindowAdmissionSkippedReason,
        ):
            raise TypeError(
                "skipped_reason must be CapacityWindowAdmissionSkippedReason"
            )

        if self.safe_preflight_summary is not None and not isinstance(
            self.safe_preflight_summary,
            CapacityAdmissionSafePreflightSummary,
        ):
            raise TypeError(
                "safe_preflight_summary must be CapacityAdmissionSafePreflightSummary"
            )

        if self.frontend_event_summary is not None and not isinstance(
            self.frontend_event_summary,
            CapacityAdmissionFrontendEventSummary,
        ):
            raise TypeError(
                "frontend_event_summary must be CapacityAdmissionFrontendEventSummary"
            )

        if not isinstance(self.log_event, CapacityWindowAdmissionLogEvent):
            raise TypeError("log_event must be CapacityWindowAdmissionLogEvent")

        if self.skipped_reason is None:
            self._validate_admitted_result()
            return

        self._validate_skipped_result()

    @property
    def admitted_count(self) -> int:
        return len(self.admitted_items)

    @property
    def started_attempt_count(self) -> int:
        return len(self.started_attempts)

    @property
    def skipped(self) -> bool:
        return self.skipped_reason is not None

    def _validate_admitted_result(self) -> None:
        if not self.admitted_items:
            raise ValueError("admitted result must include admitted_items")
        if len(self.projection_leases) != len(self.admitted_items):
            raise ValueError(
                "admitted result projection_leases length must equal "
                "admitted_items length"
            )
        if self.capacity_reservations and len(self.capacity_reservations) != len(
            self.admitted_items
        ):
            raise ValueError(
                "capacity_reservations length must equal admitted_items when present"
            )

        execution_refs = len(self.started_attempts) + len(
            self.appended_execute_command_refs
        )
        if execution_refs == 0:
            raise ValueError(
                "admitted result must include started_attempts or "
                "appended_execute_command_refs"
            )
        if execution_refs != len(self.admitted_items):
            raise ValueError(
                "started/appended execution refs count must equal admitted_items"
            )

        admitted_work_item_ids = {item.work_item_id for item in self.admitted_items}
        projection_work_item_ids = {
            lease.work_item_id for lease in self.projection_leases
        }
        if admitted_work_item_ids != projection_work_item_ids:
            raise ValueError(
                "projection leases must reference the same work items as admitted_items"
            )

        started_work_item_ids = {
            attempt.work_item_id for attempt in self.started_attempts
        }
        if started_work_item_ids and started_work_item_ids != admitted_work_item_ids:
            raise ValueError(
                "started attempts must reference admitted work items exactly"
            )

    def _validate_skipped_result(self) -> None:
        if self.admitted_items:
            raise ValueError("skipped result must not include admitted_items")
        if self.projection_leases:
            raise ValueError("skipped result must not include projection_leases")
        if self.capacity_reservations:
            raise ValueError("skipped result must not include capacity_reservations")
        if self.started_attempts:
            raise ValueError("skipped result must not include started_attempts")
        if self.appended_execute_command_refs:
            raise ValueError(
                "skipped result must not include appended_execute_command_refs"
            )
        if self.log_event is not CapacityWindowAdmissionLogEvent.PASS_SKIPPED:
            raise ValueError("skipped result log_event must be PASS_SKIPPED")


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


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


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


def _capacity_reservation_lane_matches_result_lane(
    *,
    reservation_lane: CapacityAdmissionLaneSummary,
    result_lane: CapacityAdmissionLaneSummary,
) -> bool:
    return (
        reservation_lane.work_kind == result_lane.work_kind
        and reservation_lane.provider == result_lane.provider
        and reservation_lane.model_ref == result_lane.model_ref
    )

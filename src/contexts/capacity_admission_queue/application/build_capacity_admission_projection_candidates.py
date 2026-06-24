from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneTarget:
    provider: str
    model_ref: str
    account_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider, field_name="provider")
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        if self.account_ref is not None:
            _require_non_empty_text(self.account_ref, field_name="account_ref")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionWorkItemProjectionCandidate:
    work_item_id: str
    work_kind: str
    workflow_run_id: str | None
    project_id: str | None
    provider: str
    account_ref: str | None
    model_ref: str
    status: WorkItemStatus
    retry_plan: str | None
    estimated_input_tokens: int
    estimated_output_tokens: int
    effective_output_cap_tokens: int
    reserved_total_tokens: int
    source_ref: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        _require_non_empty_text(self.work_kind, field_name="work_kind")
        if self.workflow_run_id is not None:
            _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if self.project_id is not None:
            _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(self.provider, field_name="provider")
        if self.account_ref is not None:
            _require_non_empty_text(self.account_ref, field_name="account_ref")
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        if self.status is not WorkItemStatus.READY:
            raise ValueError(
                "scheduled admission projection candidate status must be READY"
            )
        if self.retry_plan is not None:
            _require_non_empty_text(self.retry_plan, field_name="retry_plan")
        _require_positive_int(
            self.estimated_input_tokens,
            field_name="estimated_input_tokens",
        )
        _require_non_negative_int(
            self.estimated_output_tokens,
            field_name="estimated_output_tokens",
        )
        _require_non_negative_int(
            self.effective_output_cap_tokens,
            field_name="effective_output_cap_tokens",
        )
        _require_positive_int(
            self.reserved_total_tokens,
            field_name="reserved_total_tokens",
        )
        if self.effective_output_cap_tokens < self.estimated_output_tokens:
            raise ValueError(
                "effective_output_cap_tokens must be >= estimated_output_tokens",
            )
        if self.reserved_total_tokens < (
            self.estimated_input_tokens + self.estimated_output_tokens
        ):
            raise ValueError(
                "reserved_total_tokens must cover estimated input and output tokens",
            )


@dataclass(frozen=True, slots=True)
class BuildCapacityAdmissionProjectionCandidates:
    lane_target: CapacityAdmissionLaneTarget

    def __post_init__(self) -> None:
        if not isinstance(self.lane_target, CapacityAdmissionLaneTarget):
            raise TypeError("lane_target must be CapacityAdmissionLaneTarget")

    def execute(
        self,
        plans: Sequence[WorkItemSchedulePlan],
    ) -> tuple[CapacityAdmissionWorkItemProjectionCandidate, ...]:
        candidates: list[CapacityAdmissionWorkItemProjectionCandidate] = []

        for plan in plans:
            if not isinstance(plan, WorkItemSchedulePlan):
                raise TypeError("plans must contain WorkItemSchedulePlan")

            capacity_estimate = _capacity_estimate_from_payload(plan.payload)
            estimated_input_tokens = _positive_int_from_mapping(
                capacity_estimate,
                "estimated_input_tokens",
            )
            estimated_output_tokens = _non_negative_int_from_mapping(
                capacity_estimate,
                "estimated_output_tokens",
            )
            effective_output_cap_tokens = _optional_non_negative_int_from_mapping(
                capacity_estimate,
                "effective_output_cap_tokens",
            )
            if effective_output_cap_tokens is None:
                effective_output_cap_tokens = estimated_output_tokens

            reserved_total_tokens = _optional_positive_int_from_mapping(
                capacity_estimate,
                "reserved_total_tokens",
            )
            if reserved_total_tokens is None:
                reserved_total_tokens = (
                    estimated_input_tokens + effective_output_cap_tokens
                )

            candidates.append(
                CapacityAdmissionWorkItemProjectionCandidate(
                    work_item_id=plan.work_item_id,
                    work_kind=plan.work_kind.value,
                    workflow_run_id=_optional_text_from_mapping(
                        plan.payload,
                        "workflow_run_id",
                    ),
                    project_id=_optional_text_from_mapping(plan.payload, "project_id"),
                    provider=self.lane_target.provider,
                    account_ref=self.lane_target.account_ref,
                    model_ref=self.lane_target.model_ref,
                    status=WorkItemStatus.READY,
                    retry_plan=None,
                    estimated_input_tokens=estimated_input_tokens,
                    estimated_output_tokens=estimated_output_tokens,
                    effective_output_cap_tokens=effective_output_cap_tokens,
                    reserved_total_tokens=reserved_total_tokens,
                    source_ref=_source_ref_from_payload(plan.payload),
                )
            )

        return tuple(candidates)


def _capacity_estimate_from_payload(
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    value = payload.get("llm_capacity_estimate")
    if not isinstance(value, Mapping):
        raise ValueError("schedule payload must contain llm_capacity_estimate mapping")
    return value


def _source_ref_from_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    source_ref: dict[str, object] = {}

    for key in (
        "workflow_run_id",
        "project_id",
        "source_document_ref",
        "source_unit_ref",
        "phase",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            source_ref[key] = value

    return source_ref


def _optional_text_from_mapping(
    payload: Mapping[str, object],
    key: str,
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text when provided")
    return value


def _positive_int_from_mapping(payload: Mapping[str, object], key: str) -> int:
    return _positive_int_value(payload.get(key), field_name=key)


def _optional_positive_int_from_mapping(
    payload: Mapping[str, object],
    key: str,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    return _positive_int_value(value, field_name=key)


def _non_negative_int_from_mapping(payload: Mapping[str, object], key: str) -> int:
    return _non_negative_int_value(payload.get(key), field_name=key)


def _optional_non_negative_int_from_mapping(
    payload: Mapping[str, object],
    key: str,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    return _non_negative_int_value(value, field_name=key)


def _require_non_empty_text(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _positive_int_value(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive int")
    return value


def _non_negative_int_value(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative int")
    return value


def _require_positive_int(value: object, *, field_name: str) -> None:
    _positive_int_value(value, field_name=field_name)


def _require_non_negative_int(value: object, *, field_name: str) -> None:
    _non_negative_int_value(value, field_name=field_name)

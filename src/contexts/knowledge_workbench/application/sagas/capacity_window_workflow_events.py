from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)

CapacityWindowSelectionKind = Literal["fresh", "retryable"]

CLAIM_BUILDER_PREPARE_OPERATION_KEY = "prepare_claim_builder_dispatch_batch"
CLAIM_BUILDER_EXECUTE_OPERATION_KEY = "execute_claim_builder_section"
CLAIM_BUILDER_CANONICAL_PHASE = (
    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
)
DRAFT_CLAIM_COMPACTION_PREPARE_OPERATION_KEY = (
    "prepare_draft_claim_compaction_dispatch_batch"
)
DRAFT_CLAIM_COMPACTION_EXECUTE_OPERATION_KEY = "execute_draft_claim_compaction"
DRAFT_CLAIM_COMPACTION_CANONICAL_PHASE = (
    KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
)


@dataclass(frozen=True, slots=True)
class CapacityWindowExhaustionSnapshot:
    provider: str
    account_ref: str
    model_ref: str
    exhausted_reason: str
    exhausted_dimensions: tuple[str, ...]
    reset_at: datetime
    observed_at: datetime | None = None
    work_item_id: str | None = None
    dispatch_attempt_id: str | None = None
    source_unit_ref: str | None = None
    compaction_context: Mapping[str, object] | None = None


def capacity_window_key(
    *,
    provider: str,
    account_ref: str,
    model_ref: str,
) -> str:
    return f"{provider}:{account_ref}:{model_ref}"


def admission_selection_kind_from_work_item_status(
    status: WorkItemStatus,
) -> CapacityWindowSelectionKind:
    if status is WorkItemStatus.READY:
        return "fresh"
    if status is WorkItemStatus.RETRYABLE_FAILED:
        return "retryable"
    raise ValueError(
        "admission selection_kind requires READY or RETRYABLE_FAILED pre-lease status"
    )


def capacity_exhaustion_from_observation(
    *,
    capacity_observation: LlmAttemptCapacityObservation,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
) -> CapacityWindowExhaustionSnapshot | None:
    exhausted_dimensions = _exhausted_dimensions_from_observation(capacity_observation)
    if not exhausted_dimensions:
        return None

    reset_at = _reset_at_from_observation(
        capacity_observation=capacity_observation,
        exhausted_dimensions=exhausted_dimensions,
    )
    if reset_at is None:
        return None

    return CapacityWindowExhaustionSnapshot(
        provider=capacity_observation.provider,
        account_ref=capacity_observation.account_ref,
        model_ref=capacity_observation.model_ref,
        exhausted_reason="provider_capacity_limit",
        exhausted_dimensions=exhausted_dimensions,
        reset_at=reset_at,
        observed_at=capacity_observation.observed_at,
        work_item_id=work_item_id,
        dispatch_attempt_id=dispatch_attempt_id,
    )


def capacity_window_exhausted_event(
    *,
    workflow_run_id: str,
    exhaustion: CapacityWindowExhaustionSnapshot,
    operation_key: str,
    canonical_phase: str,
    occurred_at: datetime,
    causation_command_id: WorkflowCommandId | None = None,
    correlation_id: str | None = None,
) -> WorkflowEvent:
    window_key = capacity_window_key(
        provider=exhaustion.provider,
        account_ref=exhaustion.account_ref,
        model_ref=exhaustion.model_ref,
    )
    id_suffix = (
        f"{window_key}:{exhaustion.reset_at.isoformat()}"
        if correlation_id is None
        else correlation_id
    )
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "window_key": window_key,
        "provider": exhaustion.provider,
        "account_ref": exhaustion.account_ref,
        "model_ref": exhaustion.model_ref,
        "exhausted_reason": exhaustion.exhausted_reason,
        "exhausted_dimensions": list(exhaustion.exhausted_dimensions),
        "reset_at": exhaustion.reset_at.isoformat(),
        "operation_key": operation_key,
        "canonical_phase": canonical_phase,
    }
    if exhaustion.observed_at is not None:
        payload["observed_at"] = exhaustion.observed_at.isoformat()
    if exhaustion.work_item_id is not None:
        payload["work_item_id"] = exhaustion.work_item_id
    if exhaustion.dispatch_attempt_id is not None:
        payload["dispatch_attempt_id"] = exhaustion.dispatch_attempt_id
    if exhaustion.source_unit_ref is not None:
        payload["source_unit_ref"] = exhaustion.source_unit_ref
    if exhaustion.compaction_context is not None:
        payload["compaction_context"] = _compaction_context_payload(
            exhaustion.compaction_context
        )
    if causation_command_id is not None:
        payload["causation_command_id"] = causation_command_id.value

    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value}:"
            f"{id_suffix}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value
        ),
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )


def capacity_window_scheduled_wakeup_event(
    *,
    workflow_run_id: str,
    provider: str,
    account_ref: str,
    model_ref: str,
    run_after: datetime,
    reset_at: datetime,
    wakeup_command_id: WorkflowCommandId,
    prepare_command_type: str,
    wakeup_reason: str,
    operation_key: str,
    canonical_phase: str,
    occurred_at: datetime,
    compaction_context: Mapping[str, object] | None = None,
    causation_command_id: WorkflowCommandId | None = None,
) -> WorkflowEvent:
    window_key = capacity_window_key(
        provider=provider,
        account_ref=account_ref,
        model_ref=model_ref,
    )
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "window_key": window_key,
        "provider": provider,
        "account_ref": account_ref,
        "model_ref": model_ref,
        "run_after": run_after.isoformat(),
        "reset_at": reset_at.isoformat(),
        "wakeup_command_id": wakeup_command_id.value,
        "prepare_command_type": prepare_command_type,
        "wakeup_reason": wakeup_reason,
        "operation_key": operation_key,
        "canonical_phase": canonical_phase,
    }
    if compaction_context is not None:
        payload["compaction_context"] = _compaction_context_payload(compaction_context)
    if causation_command_id is not None:
        payload["causation_command_id"] = causation_command_id.value

    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_SCHEDULED_WAKEUP.value}:"
            f"{wakeup_command_id.value}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_SCHEDULED_WAKEUP.value
        ),
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=wakeup_command_id.value,
    )


def capacity_window_leased_work_item_event(
    *,
    workflow_run_id: str,
    provider: str,
    account_ref: str,
    model_ref: str,
    work_item_id: str,
    dispatch_attempt_id: str,
    lease_expires_at: datetime,
    selection_kind: CapacityWindowSelectionKind,
    occurred_at: datetime,
    source_unit_ref: str | None = None,
    token_estimate: int | None = None,
    reserved_tokens: int | None = None,
    compaction_context: Mapping[str, object] | None = None,
    causation_command_id: WorkflowCommandId | None = None,
    operation_key: str = CLAIM_BUILDER_PREPARE_OPERATION_KEY,
    canonical_phase: str = CLAIM_BUILDER_CANONICAL_PHASE,
) -> WorkflowEvent:
    window_key = capacity_window_key(
        provider=provider,
        account_ref=account_ref,
        model_ref=model_ref,
    )
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "window_key": window_key,
        "provider": provider,
        "account_ref": account_ref,
        "model_ref": model_ref,
        "work_item_id": work_item_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "lease_expires_at": lease_expires_at.isoformat(),
        "selection_kind": selection_kind,
        "operation_key": operation_key,
        "canonical_phase": canonical_phase,
    }
    if source_unit_ref is not None:
        payload["source_unit_ref"] = source_unit_ref
    if token_estimate is not None:
        payload["token_estimate"] = token_estimate
    if reserved_tokens is not None:
        payload["reserved_tokens"] = reserved_tokens
    if compaction_context is not None:
        payload["compaction_context"] = _compaction_context_payload(compaction_context)
    if causation_command_id is not None:
        payload["causation_command_id"] = causation_command_id.value

    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value}:"
            f"{dispatch_attempt_id}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value
        ),
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=dispatch_attempt_id,
    )


def source_unit_ref_from_schedule_payload(
    schedule_payload: Mapping[str, object],
) -> str | None:
    value = schedule_payload.get("source_unit_ref")
    if isinstance(value, str) and value.strip():
        return value
    return None


def compaction_context_from_schedule_payload(
    schedule_payload: Mapping[str, object],
    *,
    work_item_id: str | None = None,
    dispatch_attempt_id: str | None = None,
) -> Mapping[str, object] | None:
    raw_context: dict[str, object] = {}
    for key in (
        "group_ref",
        "batch_ref",
        "expected_output_kind",
    ):
        value = schedule_payload.get(key)
        if isinstance(value, str) and value.strip():
            raw_context[key] = value
    if work_item_id is not None:
        raw_context["work_item_id"] = work_item_id
    if dispatch_attempt_id is not None:
        raw_context["dispatch_attempt_id"] = dispatch_attempt_id
    for source_key, target_key in (
        ("source_node_refs", "input_node_refs"),
        ("node_refs", "input_node_refs"),
        ("source_claim_refs", "input_claim_refs"),
    ):
        values = _optional_text_list(schedule_payload.get(source_key))
        if values and target_key not in raw_context:
            raw_context[target_key] = list(values)
    left_node_ref = schedule_payload.get("left_node_ref")
    right_node_ref = schedule_payload.get("right_node_ref")
    if (
        "input_node_refs" not in raw_context
        and isinstance(left_node_ref, str)
        and left_node_ref.strip()
    ):
        node_refs = [left_node_ref]
        if isinstance(right_node_ref, str) and right_node_ref.strip():
            node_refs.append(right_node_ref)
        raw_context["input_node_refs"] = node_refs
    if not raw_context:
        return None
    return _compaction_context_payload(raw_context)


def _compaction_context_payload(context: Mapping[str, object]) -> Mapping[str, object]:
    allowed_text_keys = (
        "group_ref",
        "batch_ref",
        "work_item_id",
        "dispatch_attempt_id",
        "expected_output_kind",
    )
    allowed_list_keys = ("input_node_refs", "input_claim_refs")
    result: dict[str, object] = {}
    for key in allowed_text_keys:
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value
    for key in allowed_list_keys:
        values = _optional_text_list(context.get(key))
        if values:
            result[key] = list(values)
    if not result:
        raise ValueError("compaction_context must contain attachable fields")
    return result


def _optional_text_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    refs: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            refs.append(item)
    return tuple(refs)


def _exhausted_dimensions_from_observation(
    observation: LlmAttemptCapacityObservation,
) -> tuple[str, ...]:
    dimensions: list[str] = []
    if observation.remaining_minute_requests == 0:
        dimensions.append("minute_requests")
    if observation.remaining_minute_tokens == 0:
        dimensions.append("minute_tokens")
    if observation.remaining_daily_requests == 0:
        dimensions.append("daily_requests")
    if observation.remaining_daily_tokens == 0:
        dimensions.append("daily_tokens")
    return tuple(dimensions)


def _reset_at_from_observation(
    *,
    capacity_observation: LlmAttemptCapacityObservation,
    exhausted_dimensions: tuple[str, ...],
) -> datetime | None:
    minute_dimensions = {"minute_requests", "minute_tokens"}
    daily_dimensions = {"daily_requests", "daily_tokens"}
    reset_candidates: list[datetime] = []

    if any(dimension in minute_dimensions for dimension in exhausted_dimensions):
        if capacity_observation.minute_reset_at is not None:
            reset_candidates.append(capacity_observation.minute_reset_at)
    if any(dimension in daily_dimensions for dimension in exhausted_dimensions):
        if capacity_observation.daily_reset_at is not None:
            reset_candidates.append(capacity_observation.daily_reset_at)

    if not reset_candidates:
        return None
    return min(reset_candidates)

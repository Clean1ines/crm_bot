from __future__ import annotations

from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.llm_runtime.domain.routing.phase_route_policy import (
    PhaseRouteActivationScope,
    PhaseRouteActivationStatus,
    PhaseRouteKind,
    PhaseRouteReason,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def route_activation_created_event(
    *,
    workflow_run_id: str,
    canonical_phase: str,
    operation_key: str,
    route_activation_ref: str,
    work_kind: str,
    provider: str,
    model_ref: str,
    route_kind: PhaseRouteKind,
    route_reason: PhaseRouteReason,
    activation_scope: PhaseRouteActivationScope,
    status: PhaseRouteActivationStatus,
    occurred_at: datetime,
    target_work_item_id: str | None = None,
    causation_command_id: WorkflowCommandId | None = None,
    correlation_id: str | None = None,
) -> WorkflowEvent:
    return _route_event(
        event_type=KnowledgeExtractionCanonicalEventType.ROUTE_ACTIVATION_CREATED.value,
        workflow_run_id=workflow_run_id,
        canonical_phase=canonical_phase,
        operation_key=operation_key,
        route_activation_ref=route_activation_ref,
        work_kind=work_kind,
        provider=provider,
        model_ref=model_ref,
        route_kind=route_kind,
        route_reason=route_reason,
        activation_scope=activation_scope,
        status=status,
        target_work_item_id=target_work_item_id,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )


def route_activation_closed_event(
    *,
    workflow_run_id: str,
    canonical_phase: str,
    operation_key: str,
    route_activation_ref: str,
    work_kind: str,
    provider: str,
    model_ref: str,
    route_kind: PhaseRouteKind,
    route_reason: PhaseRouteReason,
    activation_scope: PhaseRouteActivationScope,
    status: PhaseRouteActivationStatus,
    occurred_at: datetime,
    target_work_item_id: str | None = None,
    causation_command_id: WorkflowCommandId | None = None,
    correlation_id: str | None = None,
) -> WorkflowEvent:
    return _route_event(
        event_type=KnowledgeExtractionCanonicalEventType.ROUTE_ACTIVATION_CLOSED.value,
        workflow_run_id=workflow_run_id,
        canonical_phase=canonical_phase,
        operation_key=operation_key,
        route_activation_ref=route_activation_ref,
        work_kind=work_kind,
        provider=provider,
        model_ref=model_ref,
        route_kind=route_kind,
        route_reason=route_reason,
        activation_scope=activation_scope,
        status=status,
        target_work_item_id=target_work_item_id,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )


def work_item_reroute_requested_event(
    *,
    workflow_run_id: str,
    canonical_phase: str,
    operation_key: str,
    work_item_id: str,
    work_kind: str,
    previous_route_activation_ref: str,
    next_route_activation_ref: str,
    route_reason: PhaseRouteReason,
    occurred_at: datetime,
    source_unit_ref: str | None = None,
    previous_model_ref: str | None = None,
    next_model_ref: str | None = None,
    estimated_input_tokens: int | None = None,
    reserved_total_tokens: int | None = None,
    causation_command_id: WorkflowCommandId | None = None,
    correlation_id: str | None = None,
) -> WorkflowEvent:
    return _reroute_event(
        event_type=KnowledgeExtractionCanonicalEventType.WORK_ITEM_REROUTE_REQUESTED.value,
        workflow_run_id=workflow_run_id,
        canonical_phase=canonical_phase,
        operation_key=operation_key,
        work_item_id=work_item_id,
        work_kind=work_kind,
        previous_route_activation_ref=previous_route_activation_ref,
        next_route_activation_ref=next_route_activation_ref,
        route_reason=route_reason,
        occurred_at=occurred_at,
        source_unit_ref=source_unit_ref,
        previous_model_ref=previous_model_ref,
        next_model_ref=next_model_ref,
        estimated_input_tokens=estimated_input_tokens,
        reserved_total_tokens=reserved_total_tokens,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )


def work_item_rerouted_event(
    *,
    workflow_run_id: str,
    canonical_phase: str,
    operation_key: str,
    work_item_id: str,
    work_kind: str,
    previous_route_activation_ref: str,
    next_route_activation_ref: str,
    route_reason: PhaseRouteReason,
    occurred_at: datetime,
    source_unit_ref: str | None = None,
    previous_model_ref: str | None = None,
    next_model_ref: str | None = None,
    estimated_input_tokens: int | None = None,
    reserved_total_tokens: int | None = None,
    causation_command_id: WorkflowCommandId | None = None,
    correlation_id: str | None = None,
) -> WorkflowEvent:
    return _reroute_event(
        event_type=KnowledgeExtractionCanonicalEventType.WORK_ITEM_REROUTED.value,
        workflow_run_id=workflow_run_id,
        canonical_phase=canonical_phase,
        operation_key=operation_key,
        work_item_id=work_item_id,
        work_kind=work_kind,
        previous_route_activation_ref=previous_route_activation_ref,
        next_route_activation_ref=next_route_activation_ref,
        route_reason=route_reason,
        occurred_at=occurred_at,
        source_unit_ref=source_unit_ref,
        previous_model_ref=previous_model_ref,
        next_model_ref=next_model_ref,
        estimated_input_tokens=estimated_input_tokens,
        reserved_total_tokens=reserved_total_tokens,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )


def _route_event(
    *,
    event_type: str,
    workflow_run_id: str,
    canonical_phase: str,
    operation_key: str,
    route_activation_ref: str,
    work_kind: str,
    provider: str,
    model_ref: str,
    route_kind: PhaseRouteKind,
    route_reason: PhaseRouteReason,
    activation_scope: PhaseRouteActivationScope,
    status: PhaseRouteActivationStatus,
    target_work_item_id: str | None,
    occurred_at: datetime,
    causation_command_id: WorkflowCommandId | None,
    correlation_id: str | None,
) -> WorkflowEvent:
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "canonical_phase": canonical_phase,
        "operation_key": operation_key,
        "route_activation_ref": route_activation_ref,
        "work_kind": work_kind,
        "provider": provider,
        "model_ref": model_ref,
        "route_kind": route_kind.value,
        "route_reason": route_reason.value,
        "activation_scope": activation_scope.value,
        "status": status.value,
    }
    if target_work_item_id is not None:
        payload["target_work_item_id"] = target_work_item_id
    if causation_command_id is not None:
        payload["causation_command_id"] = causation_command_id.value

    event_suffix = (
        correlation_id if correlation_id is not None else route_activation_ref
    )
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{workflow_run_id}:{event_type}:{event_suffix}"
        ),
        event_type=event_type,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )


def _reroute_event(
    *,
    event_type: str,
    workflow_run_id: str,
    canonical_phase: str,
    operation_key: str,
    work_item_id: str,
    work_kind: str,
    previous_route_activation_ref: str,
    next_route_activation_ref: str,
    route_reason: PhaseRouteReason,
    occurred_at: datetime,
    source_unit_ref: str | None,
    previous_model_ref: str | None,
    next_model_ref: str | None,
    estimated_input_tokens: int | None,
    reserved_total_tokens: int | None,
    causation_command_id: WorkflowCommandId | None,
    correlation_id: str | None,
) -> WorkflowEvent:
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "canonical_phase": canonical_phase,
        "operation_key": operation_key,
        "work_item_id": work_item_id,
        "work_kind": work_kind,
        "previous_route_activation_ref": previous_route_activation_ref,
        "next_route_activation_ref": next_route_activation_ref,
        "route_reason": route_reason.value,
    }
    if source_unit_ref is not None:
        payload["source_unit_ref"] = source_unit_ref
    if previous_model_ref is not None:
        payload["previous_model_ref"] = previous_model_ref
    if next_model_ref is not None:
        payload["next_model_ref"] = next_model_ref
    if estimated_input_tokens is not None:
        payload["estimated_input_tokens"] = estimated_input_tokens
    if reserved_total_tokens is not None:
        payload["reserved_total_tokens"] = reserved_total_tokens
    if causation_command_id is not None:
        payload["causation_command_id"] = causation_command_id.value

    event_suffix = correlation_id if correlation_id is not None else work_item_id
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{workflow_run_id}:{event_type}:{event_suffix}"
        ),
        event_type=event_type,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=causation_command_id,
        correlation_id=correlation_id,
    )

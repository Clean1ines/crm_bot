from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionDispatchContextSummary,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_window_budget_repository_port import (
    CapacityReservation,
)
from src.contexts.capacity_admission_queue.application.run_capacity_window_drain import (
    CapacityDrainStrategyResult,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


CLAIM_BUILDER_SECTION_WORK_KIND = "knowledge_workbench.claim_builder.section_extraction"


class ClaimBuilderDrainDispatchContextResolverPort(Protocol):
    async def resolve_dispatch_context(
        self,
        *,
        work_item_id: str,
    ) -> CapacityAdmissionDispatchContextSummary | None: ...


@dataclass(frozen=True, slots=True)
class ClaimBuilderCapacityDrainBridge:
    workflow_run_id: str
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort
    dispatch_context_resolver: ClaimBuilderDrainDispatchContextResolverPort
    source_document_ref: str | None = None
    active_model_ref: str | None = None
    scheduled_work_item_count: int | None = None

    async def should_pause(
        self,
        *,
        workflow_run_id: str | None,
        now: datetime,
    ) -> bool:
        return False

    async def execute_admitted_work_item(
        self,
        *,
        work_item_id: str,
        selection_lane_key: CapacityAdmissionLaneKey,
        execution_window_key: CapacityAdmissionLaneKey,
        reservation: CapacityReservation,
        worker_ref: str,
        now: datetime,
    ) -> CapacityDrainStrategyResult:
        dispatch_attempt_id = _dispatch_attempt_id(
            workflow_run_id=self.workflow_run_id,
            work_item_id=work_item_id,
            account_ref=execution_window_key.account_ref,
        )
        dispatch_context = (
            await self.dispatch_context_resolver.resolve_dispatch_context(
                work_item_id=work_item_id,
            )
        )
        command = _execute_claim_builder_section_command(
            workflow_run_id=self.workflow_run_id,
            work_item_id=work_item_id,
            dispatch_attempt_id=dispatch_attempt_id,
            source_document_ref=self.source_document_ref,
            scheduled_work_item_count=self.scheduled_work_item_count,
            active_model_ref=self.active_model_ref or execution_window_key.model_ref,
            dispatch_context=dispatch_context,
            occurred_at=now,
        )
        await self.workflow_unit_of_work.command_log.append_pending_command(command)
        await self.workflow_unit_of_work.outbox.append_event(
            _prepared_attempt_event(
                workflow_run_id=self.workflow_run_id,
                work_item_id=work_item_id,
                dispatch_attempt_id=dispatch_attempt_id,
                selection_lane_key=selection_lane_key,
                execution_window_key=execution_window_key,
                reservation=reservation,
                dispatch_context=dispatch_context,
                occurred_at=now,
            )
        )
        return CapacityDrainStrategyResult(
            work_item_id=work_item_id,
            dispatch_attempt_id=dispatch_attempt_id,
            provider_call_started=False,
            capacity_observation_recorded=False,
        )


def _execute_claim_builder_section_command(
    *,
    workflow_run_id: str,
    work_item_id: str,
    dispatch_attempt_id: str,
    source_document_ref: str | None,
    scheduled_work_item_count: int | None,
    active_model_ref: str,
    dispatch_context: CapacityAdmissionDispatchContextSummary | None,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        f"execute-claim-builder-section:{workflow_run_id}:{dispatch_attempt_id}"
    )
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "claim_builder_prepare_command_id": (
            f"capacity-drain-bridge:{workflow_run_id}:{dispatch_attempt_id}"
        ),
        "claim_builder_prepare_idempotency_key": (
            f"capacity-drain-bridge:{workflow_run_id}:{dispatch_attempt_id}"
        ),
        "active_model_ref": active_model_ref,
        "llm_dispatch_preparation": {
            "active_model_ref": active_model_ref,
            "bridge": "claim_builder_capacity_drain",
        },
    }
    if source_document_ref is not None:
        payload["source_document_ref"] = source_document_ref
    if scheduled_work_item_count is not None:
        payload["scheduled_work_item_count"] = scheduled_work_item_count
    if dispatch_context is not None:
        if dispatch_context.source_ref is not None:
            payload["source_ref"] = dispatch_context.source_ref
        if dispatch_context.source_unit_ref is not None:
            payload["source_unit_ref"] = dispatch_context.source_unit_ref

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _prepared_attempt_event(
    *,
    workflow_run_id: str,
    work_item_id: str,
    dispatch_attempt_id: str,
    selection_lane_key: CapacityAdmissionLaneKey,
    execution_window_key: CapacityAdmissionLaneKey,
    reservation: CapacityReservation,
    dispatch_context: CapacityAdmissionDispatchContextSummary | None,
    occurred_at: datetime,
) -> WorkflowEvent:
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "work_item_id": work_item_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND,
        "provider": execution_window_key.provider,
        "account_ref": execution_window_key.account_ref,
        "model_ref": execution_window_key.model_ref,
        "selection_account_ref": selection_lane_key.account_ref,
        "reserved_requests": reservation.request_count,
        "reserved_tokens": reservation.token_count,
    }
    if dispatch_context is not None:
        if dispatch_context.source_ref is not None:
            payload["source_ref"] = dispatch_context.source_ref
        if dispatch_context.source_unit_ref is not None:
            payload["source_unit_ref"] = dispatch_context.source_unit_ref

    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value}:"
            f"{dispatch_attempt_id}"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value
        ),
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=None,
        correlation_id=dispatch_attempt_id,
    )


def _dispatch_attempt_id(
    *,
    workflow_run_id: str,
    work_item_id: str,
    account_ref: str | None,
) -> str:
    material = f"{workflow_run_id}:{work_item_id}:{account_ref or '-'}"
    return f"claim-builder-capacity-drain:{uuid5(NAMESPACE_URL, material)}"

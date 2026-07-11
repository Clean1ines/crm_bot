from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.append_capacity_window_prepare_wakeup import (
    append_capacity_window_prepare_wakeup,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_adjudication import (
    ExecuteWorkbenchRagEvalAdjudicationCommand,
    ExecuteWorkbenchRagEvalAdjudicationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowEventType,
    WorkbenchRagEvalWorkflowPhase,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


class ExecuteWorkbenchRagEvalAdjudicationPort(Protocol):
    async def execute(
        self,
        command: ExecuteWorkbenchRagEvalAdjudicationCommand,
    ) -> ExecuteWorkbenchRagEvalAdjudicationResult: ...


@dataclass(frozen=True, slots=True)
class HandleExecuteWorkbenchRagEvalAdjudicationCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleExecuteWorkbenchRagEvalAdjudicationResult:
    saved_adjudication_count: int
    outcome_status: str
    completed_command_id: WorkflowCommandId


class HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler:
    async def execute(
        self,
        command: HandleExecuteWorkbenchRagEvalAdjudicationCommand,
        *,
        adjudication_executor: ExecuteWorkbenchRagEvalAdjudicationPort,
        capacity_observation_repository: LlmAttemptCapacityObservationRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleExecuteWorkbenchRagEvalAdjudicationResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION.value
            or workflow_command.status is not WorkflowCommandStatus.PENDING
        ):
            raise ValueError("workflow command must be pending adjudication execute")
        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        dispatch_attempt_id = _payload_text(
            workflow_command.payload,
            "dispatch_attempt_id",
        )
        expected_work_item_id = _payload_text(workflow_command.payload, "work_item_id")
        execution_result = await adjudication_executor.execute(
            ExecuteWorkbenchRagEvalAdjudicationCommand(
                dispatch_attempt_id=dispatch_attempt_id
            )
        )
        if execution_result.work_item_id != expected_work_item_id:
            raise ValueError("execution result work_item_id must match command")
        capacity_observation = _capacity_observation(
            execution_result.capacity_observation
        )
        if capacity_observation is not None:
            await capacity_observation_repository.record_observation(
                capacity_observation
            )
            await workflow_unit_of_work.outbox.append_event(
                _capacity_event(
                    workflow_command,
                    workflow_run_id,
                    execution_result,
                    capacity_observation,
                )
            )
            await append_capacity_window_prepare_wakeup(
                workflow_unit_of_work=workflow_unit_of_work,
                source_command=workflow_command,
                workflow_run_id=workflow_run_id,
                prepare_command_type=(
                    WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH
                ),
                capacity_observation=capacity_observation,
                occurred_at=execution_result.finished_at,
            )
        await workflow_unit_of_work.outbox.append_event(
            _attempt_event(workflow_command, workflow_run_id, execution_result)
        )
        await workflow_unit_of_work.command_log.append_pending_command(
            _reconcile_command(workflow_command, workflow_run_id, execution_result)
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=f"timeline:{workflow_run_id}:adjudication-attempt-completed:{workflow_command.command_id.value}",
                workflow_run_id=workflow_run_id,
                event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_ATTEMPT_COMPLETED.value,
                phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="RAG Eval adjudication attempt completed",
                payload_summary={
                    "outcome_status": execution_result.outcome_status,
                    "saved_adjudication_count": execution_result.saved_adjudication_count,
                },
                occurred_at=execution_result.finished_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=execution_result.finished_at,
        )
        return HandleExecuteWorkbenchRagEvalAdjudicationResult(
            saved_adjudication_count=execution_result.saved_adjudication_count,
            outcome_status=execution_result.outcome_status,
            completed_command_id=workflow_command.command_id,
        )


def _capacity_observation(
    payload: Mapping[str, object] | None,
) -> LlmAttemptCapacityObservation | None:
    if payload is None:
        return None
    return LlmAttemptCapacityObservation.from_payload(payload)


def _attempt_event(
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    execution_result: ExecuteWorkbenchRagEvalAdjudicationResult,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{WorkbenchRagEvalWorkflowEventType.ADJUDICATION_ATTEMPT_COMPLETED.value}:"
            f"{execution_result.dispatch_attempt_id}"
        ),
        event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_ATTEMPT_COMPLETED.value,
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": workflow_run_id,
            "work_kind": WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND.value,
            "dispatch_attempt_id": execution_result.dispatch_attempt_id,
            "work_item_id": execution_result.work_item_id,
            "outcome_status": execution_result.outcome_status,
            "saved_adjudication_count": execution_result.saved_adjudication_count,
            "error_kind": execution_result.error_kind,
            "next_attempt_at": execution_result.next_attempt_at.isoformat()
            if execution_result.next_attempt_at is not None
            else None,
        },
        occurred_at=execution_result.finished_at,
        causation_command_id=workflow_command.command_id,
    )


def _capacity_event(
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    execution_result: ExecuteWorkbenchRagEvalAdjudicationResult,
    capacity_observation: LlmAttemptCapacityObservation,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{WorkbenchRagEvalWorkflowEventType.ADJUDICATION_CAPACITY_OBSERVED.value}:"
            f"{execution_result.dispatch_attempt_id}"
        ),
        event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_CAPACITY_OBSERVED.value,
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": workflow_run_id,
            "work_kind": WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND.value,
            "dispatch_attempt_id": execution_result.dispatch_attempt_id,
            "provider": capacity_observation.provider,
            "account_ref": capacity_observation.account_ref,
            "model_ref": capacity_observation.model_ref,
            "outcome_class": capacity_observation.outcome_class,
        },
        occurred_at=execution_result.finished_at,
        causation_command_id=workflow_command.command_id,
    )


def _reconcile_command(
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    execution_result: ExecuteWorkbenchRagEvalAdjudicationResult,
) -> WorkflowCommand:
    command_type = WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS
    key = (
        f"rag-eval:{workflow_run_id}:{command_type.value}:"
        f"{execution_result.dispatch_attempt_id}"
    )
    payload = dict(workflow_command.payload)
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{key}"),
        command_type=command_type.value,
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=execution_result.finished_at,
        created_at=execution_result.finished_at,
        updated_at=execution_result.finished_at,
    )


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload.{key} must be non-empty")
    return value.strip()

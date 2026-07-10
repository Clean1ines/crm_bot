from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.append_capacity_window_prepare_wakeup import (
    append_capacity_window_prepare_wakeup,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation import (
    ExecuteWorkbenchRagEvalQuestionGenerationCommand,
    ExecuteWorkbenchRagEvalQuestionGenerationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
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
from src.contexts.workflow_runtime.domain.entities.workflow_event import (
    WorkflowEvent,
)
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


class ExecuteWorkbenchRagEvalQuestionGenerationPort(Protocol):
    async def execute(
        self,
        command: ExecuteWorkbenchRagEvalQuestionGenerationCommand,
    ) -> ExecuteWorkbenchRagEvalQuestionGenerationResult: ...


@dataclass(frozen=True, slots=True)
class HandleExecuteWorkbenchRagEvalQuestionGenerationCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleExecuteWorkbenchRagEvalQuestionGenerationResult:
    workflow_run_id: str
    dispatch_attempt_id: str
    work_item_id: str
    outcome_status: str
    saved_question_count: int
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId


class HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler:
    async def execute(
        self,
        command: HandleExecuteWorkbenchRagEvalQuestionGenerationCommand,
        *,
        question_generation_executor: (ExecuteWorkbenchRagEvalQuestionGenerationPort),
        capacity_observation_repository: (LlmAttemptCapacityObservationRepositoryPort),
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleExecuteWorkbenchRagEvalQuestionGenerationResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)

        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        dispatch_attempt_id = _payload_text(
            workflow_command.payload,
            "dispatch_attempt_id",
        )
        expected_work_item_id = _payload_text(
            workflow_command.payload,
            "work_item_id",
        )

        execution_result = await question_generation_executor.execute(
            ExecuteWorkbenchRagEvalQuestionGenerationCommand(
                dispatch_attempt_id=dispatch_attempt_id,
            )
        )
        if execution_result.dispatch_attempt_id != dispatch_attempt_id:
            raise ValueError("execution result dispatch_attempt_id must match command")
        if execution_result.work_item_id != expected_work_item_id:
            raise ValueError("execution result work_item_id must match command")

        capacity_observation = _capacity_observation(
            execution_result.capacity_observation,
        )
        appended_event_count = 0
        appended_next_command_count = 0

        if capacity_observation is not None:
            await capacity_observation_repository.record_observation(
                capacity_observation
            )
            await workflow_unit_of_work.outbox.append_event(
                _capacity_observed_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    dispatch_attempt_id=dispatch_attempt_id,
                    work_item_id=expected_work_item_id,
                    capacity_observation=capacity_observation,
                    occurred_at=execution_result.finished_at,
                )
            )
            appended_event_count += 1

            wakeup = await append_capacity_window_prepare_wakeup(
                workflow_unit_of_work=workflow_unit_of_work,
                source_command=workflow_command,
                workflow_run_id=workflow_run_id,
                prepare_command_type=(
                    WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH
                ),
                capacity_observation=capacity_observation,
                occurred_at=execution_result.finished_at,
            )
            if wakeup is not None:
                appended_next_command_count += 1

        await workflow_unit_of_work.outbox.append_event(
            _attempt_completed_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                execution_result=execution_result,
            )
        )
        appended_event_count += 1

        await workflow_unit_of_work.command_log.append_pending_command(
            _reconcile_command(
                source_command=workflow_command,
                workflow_run_id=workflow_run_id,
                execution_result=execution_result,
            )
        )
        appended_next_command_count += 1

        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                execution_result=execution_result,
            )
        )

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=execution_result.finished_at,
        )

        return HandleExecuteWorkbenchRagEvalQuestionGenerationResult(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=expected_work_item_id,
            outcome_status=execution_result.outcome_status,
            saved_question_count=execution_result.saved_question_count,
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(
    workflow_command: WorkflowCommand,
) -> None:
    if workflow_command.command_type != (
        WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION.value
    ):
        raise ValueError("workflow command must be ExecuteRagEvalQuestionGeneration")
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow command status must be PENDING")


def _capacity_observation(
    payload: Mapping[str, object] | None,
) -> LlmAttemptCapacityObservation | None:
    if payload is None:
        return None
    return LlmAttemptCapacityObservation.from_payload(payload)


def _attempt_completed_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    execution_result: ExecuteWorkbenchRagEvalQuestionGenerationResult,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_ATTEMPT_COMPLETED.value}:"
            f"{execution_result.dispatch_attempt_id}"
        ),
        event_type=(
            WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_ATTEMPT_COMPLETED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": workflow_run_id,
            "project_id": _payload_text(
                workflow_command.payload,
                "project_id",
            ),
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
            "dispatch_attempt_id": (execution_result.dispatch_attempt_id),
            "work_item_id": execution_result.work_item_id,
            "outcome_status": execution_result.outcome_status,
            "saved_question_count": (execution_result.saved_question_count),
            "error_kind": execution_result.error_kind,
            "next_attempt_at": (
                execution_result.next_attempt_at.isoformat()
                if execution_result.next_attempt_at is not None
                else None
            ),
        },
        occurred_at=execution_result.finished_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _capacity_observed_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    capacity_observation: LlmAttemptCapacityObservation,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_CAPACITY_OBSERVED.value}:"
            f"{dispatch_attempt_id}"
        ),
        event_type=(
            WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_CAPACITY_OBSERVED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": workflow_run_id,
            "project_id": _payload_text(
                workflow_command.payload,
                "project_id",
            ),
            "dispatch_attempt_id": dispatch_attempt_id,
            "work_item_id": work_item_id,
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
            **capacity_observation.to_event_payload(),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _reconcile_command(
    *,
    source_command: WorkflowCommand,
    workflow_run_id: str,
    execution_result: ExecuteWorkbenchRagEvalQuestionGenerationResult,
) -> WorkflowCommand:
    idempotency_key = (
        "reconcile-rag-eval-question-generation:"
        f"{workflow_run_id}:"
        f"{execution_result.dispatch_attempt_id}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": workflow_run_id,
            "rag_eval_run_id": workflow_run_id,
            "project_id": _payload_text(
                source_command.payload,
                "project_id",
            ),
            "publication_id": source_command.payload.get("publication_id"),
            "source_document_ref": source_command.payload.get("source_document_ref"),
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
            "causation_dispatch_attempt_id": (execution_result.dispatch_attempt_id),
            "causation_work_item_id": execution_result.work_item_id,
            "outcome_status": execution_result.outcome_status,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=execution_result.finished_at,
        created_at=execution_result.finished_at,
        updated_at=execution_result.finished_at,
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    execution_result: ExecuteWorkbenchRagEvalQuestionGenerationResult,
) -> WorkflowTimelineEntry:
    severity = (
        WorkflowTimelineSeverity.INFO
        if execution_result.outcome_status == "succeeded"
        else WorkflowTimelineSeverity.WARNING
    )
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            "RagEvalQuestionGenerationAttemptCompleted:"
            f"{execution_result.dispatch_attempt_id}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=(
            WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_ATTEMPT_COMPLETED.value
        ),
        phase=WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION.value,
        severity=severity,
        message=("RAG Eval question-generation attempt completed"),
        payload_summary={
            "workflow_family": "workbench_rag_eval",
            "dispatch_attempt_id": (execution_result.dispatch_attempt_id),
            "work_item_id": execution_result.work_item_id,
            "outcome_status": execution_result.outcome_status,
            "saved_question_count": (execution_result.saved_question_count),
            "error_kind": execution_result.error_kind,
            "next_attempt_at": (
                execution_result.next_attempt_at.isoformat()
                if execution_result.next_attempt_at is not None
                else None
            ),
        },
        occurred_at=execution_result.finished_at,
        source_ref=execution_result.work_item_id,
    )


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value

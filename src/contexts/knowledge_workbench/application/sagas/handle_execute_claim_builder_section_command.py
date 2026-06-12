from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionStatus,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
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
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)


class ExecutePreparedLlmDispatchAttemptPort(Protocol):
    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class HandleExecuteClaimBuilderSectionCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleExecuteClaimBuilderSectionResult:
    workflow_run_id: str
    dispatch_attempt_id: str
    work_item_id: str
    outcome_status: str
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.dispatch_attempt_id, "dispatch_attempt_id")
        _require_non_empty_text(self.work_item_id, "work_item_id")
        _require_non_empty_text(self.outcome_status, "outcome_status")
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandleExecuteClaimBuilderSectionCommandHandler:
    async def execute(
        self,
        command: HandleExecuteClaimBuilderSectionCommand,
        *,
        execute_prepared_llm_dispatch_attempt: ExecutePreparedLlmDispatchAttemptPort,
        capacity_observation_repository: LlmAttemptCapacityObservationRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleExecuteClaimBuilderSectionResult:
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
        work_item_id = _payload_text(workflow_command.payload, "work_item_id")

        execution_result = cast(
            ExecutePreparedLlmDispatchAttemptResult,
            await execute_prepared_llm_dispatch_attempt.execute(
                ExecutePreparedLlmDispatchAttemptCommand(
                    attempt_id=dispatch_attempt_id,
                ),
            ),
        )
        if execution_result.dispatch.work_item_id != work_item_id:
            raise ValueError(
                "dispatch work_item_id must match workflow command payload"
            )

        finished_at = execution_result.llm_result.finished_at
        outcome_status = execution_result.llm_result.status.value

        capacity_observation = _capacity_observation_from_result(execution_result)
        appended_event_count = 0

        if capacity_observation is not None:
            await capacity_observation_repository.record_observation(
                capacity_observation,
            )
            await workflow_unit_of_work.outbox.append_event(
                _capacity_observed_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    dispatch_attempt_id=dispatch_attempt_id,
                    work_item_id=work_item_id,
                    capacity_observation=capacity_observation,
                    occurred_at=finished_at,
                ),
            )
            appended_event_count += 1

        outcome_event = _claim_builder_attempt_outcome_event(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
        )
        await workflow_unit_of_work.outbox.append_event(outcome_event)
        appended_event_count += 1

        next_command = _reconcile_claim_builder_progress_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            occurred_at=finished_at,
        )
        await workflow_unit_of_work.command_log.append_pending_command(next_command)

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            status=execution_result.llm_result.status,
            capacity_observation=capacity_observation,
            occurred_at=finished_at,
        )

        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                dispatch_attempt_id=dispatch_attempt_id,
                work_item_id=work_item_id,
                execution_result=execution_result,
                capacity_observation=capacity_observation,
            ),
        )

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=finished_at,
        )

        return HandleExecuteClaimBuilderSectionResult(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            outcome_status=outcome_status,
            appended_event_count=appended_event_count,
            appended_next_command_count=1,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    ):
        raise ValueError(
            "workflow_command command_type must be ExecuteClaimBuilderSection"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _capacity_observation_from_result(
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
) -> LlmAttemptCapacityObservation | None:
    payload = execution_result.llm_result.capacity_observation
    if payload is None:
        return None
    return LlmAttemptCapacityObservation.from_payload(payload)


def _capacity_observed_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    capacity_observation: LlmAttemptCapacityObservation,
    occurred_at,
) -> WorkflowEvent:
    payload = {
        "workflow_run_id": workflow_run_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        **capacity_observation.to_event_payload(),
    }
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value}:"
            f"{dispatch_attempt_id}"
        ),
        event_type=KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=dispatch_attempt_id,
    )


def _claim_builder_attempt_outcome_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
) -> WorkflowEvent:
    event_type = _event_type_for_status(execution_result.llm_result.status)
    payload = _event_payload(
        workflow_run_id=workflow_run_id,
        dispatch_attempt_id=dispatch_attempt_id,
        work_item_id=work_item_id,
        execution_result=execution_result,
        capacity_observation=capacity_observation,
    )
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{workflow_run_id}:{event_type.value}:{dispatch_attempt_id}"
        ),
        event_type=event_type.value,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=execution_result.llm_result.finished_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=dispatch_attempt_id,
    )


def _event_type_for_status(
    status: LlmDispatchExecutionStatus,
) -> KnowledgeExtractionCanonicalEventType:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED
    if status is LlmDispatchExecutionStatus.DEFERRED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED
    if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED
    if status is LlmDispatchExecutionStatus.TERMINAL_FAILED:
        return KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED
    raise ValueError("unsupported LLM dispatch execution status")


def _event_payload(
    *,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
) -> dict[str, object]:
    capacity_payload = (
        capacity_observation.to_event_payload()
        if capacity_observation is not None
        else _allocation_payload(execution_result.dispatch.dispatch_payload)
    )
    return {
        "workflow_run_id": workflow_run_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "outcome_status": execution_result.llm_result.status.value,
        "error_kind": execution_result.llm_result.error_kind,
        "next_attempt_at": _datetime_payload(
            execution_result.llm_result.next_attempt_at
        ),
        "provider": capacity_payload.get("provider"),
        "account_ref": capacity_payload.get("account_ref"),
        "model_ref": capacity_payload.get("model_ref"),
        "actual_prompt_tokens": capacity_payload.get("actual_prompt_tokens"),
        "actual_completion_tokens": capacity_payload.get("actual_completion_tokens"),
        "actual_total_tokens": capacity_payload.get("actual_total_tokens"),
    }


def _allocation_payload(dispatch_payload: Mapping[str, object]) -> dict[str, object]:
    allocation = dispatch_payload.get("llm_allocation")
    if not isinstance(allocation, Mapping):
        return {}
    return {
        "provider": allocation.get("provider"),
        "account_ref": allocation.get("account_ref"),
        "model_ref": allocation.get("model_ref"),
    }


def _reconcile_claim_builder_progress_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    occurred_at,
) -> WorkflowCommand:
    idempotency_key = (
        f"reconcile-claim-builder-progress:{workflow_run_id}:{dispatch_attempt_id}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=_reconcile_command_payload(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
        ),
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _reconcile_command_payload(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "workflow_run_id": workflow_run_id,
        "dispatch_attempt_id": dispatch_attempt_id,
        "work_item_id": work_item_id,
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
    }
    dispatch_preparation = workflow_command.payload.get("llm_dispatch_preparation")
    if dispatch_preparation is not None:
        if not isinstance(dispatch_preparation, Mapping):
            raise ValueError("llm_dispatch_preparation must be mapping")
        payload["llm_dispatch_preparation"] = dict(dispatch_preparation)
    return payload


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    status: LlmDispatchExecutionStatus,
    capacity_observation: LlmAttemptCapacityObservation | None,
    occurred_at,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["executed_attempt_count"] = (
        domain_counters.get("executed_attempt_count", 0) + 1
    )
    if capacity_observation is not None:
        domain_counters["capacity_observation_count"] = (
            domain_counters.get("capacity_observation_count", 0) + 1
        )

    completed_delta = 1 if status is LlmDispatchExecutionStatus.SUCCEEDED else 0
    deferred_delta = 1 if status is LlmDispatchExecutionStatus.DEFERRED else 0
    retryable_delta = 1 if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED else 0
    terminal_delta = 1 if status is LlmDispatchExecutionStatus.TERMINAL_FAILED else 0

    running_before = existing.running_work_items if existing is not None else 0

    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
            running_work_items=max(0, running_before - 1),
            completed_work_items=(
                (existing.completed_work_items if existing is not None else 0)
                + completed_delta
            ),
            deferred_work_items=(
                (existing.deferred_work_items if existing is not None else 0)
                + deferred_delta
            ),
            retryable_failed_work_items=(
                (existing.retryable_failed_work_items if existing is not None else 0)
                + retryable_delta
            ),
            terminal_failed_work_items=(
                (existing.terminal_failed_work_items if existing is not None else 0)
                + terminal_delta
            ),
            blocked_work_items=existing.blocked_work_items
            if existing is not None
            else 0,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        ),
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    dispatch_attempt_id: str,
    work_item_id: str,
    execution_result: ExecutePreparedLlmDispatchAttemptResult,
    capacity_observation: LlmAttemptCapacityObservation | None,
) -> WorkflowTimelineEntry:
    event_type = _event_type_for_status(execution_result.llm_result.status)
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            f"ClaimBuilderSectionAttemptExecuted:{dispatch_attempt_id}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=event_type.value,
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        severity=_severity_for_status(execution_result.llm_result.status),
        message="Claim builder section attempt executed",
        payload_summary=_event_payload(
            workflow_run_id=workflow_run_id,
            dispatch_attempt_id=dispatch_attempt_id,
            work_item_id=work_item_id,
            execution_result=execution_result,
            capacity_observation=capacity_observation,
        ),
        occurred_at=execution_result.llm_result.finished_at,
        source_ref=workflow_command.command_type,
        work_item_id=work_item_id,
        attempt_id=dispatch_attempt_id,
    )


def _severity_for_status(
    status: LlmDispatchExecutionStatus,
) -> WorkflowTimelineSeverity:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        return WorkflowTimelineSeverity.INFO
    if status in {
        LlmDispatchExecutionStatus.DEFERRED,
        LlmDispatchExecutionStatus.RETRYABLE_FAILED,
    }:
        return WorkflowTimelineSeverity.WARNING
    return WorkflowTimelineSeverity.ERROR


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


def _datetime_payload(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")

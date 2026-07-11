from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
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
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)


class PrepareLlmDispatchBatchPort(Protocol):
    async def execute(
        self,
        command: PrepareLlmDispatchBatchCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchResult:
    prepared_dispatch_count: int
    rescheduled_at: datetime | None


class HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommandHandler:
    async def execute(
        self,
        command: HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommand,
        *,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH.value
            or workflow_command.status is not WorkflowCommandStatus.PENDING
        ):
            raise ValueError("workflow command must be pending adjudication prepare")
        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        occurred_at = max(datetime.now(timezone.utc), workflow_command.updated_at)
        requested_items = _payload_positive_int(
            workflow_command.payload,
            "scheduled_work_item_count",
        )
        prepare_result = await prepare_llm_dispatch_batch.execute(
            PrepareLlmDispatchBatchCommand(
                work_kind=WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
                requested_items=requested_items,
                worker=WorkerRef("knowledge-workbench-rag-eval-adjudication"),
                lease_token_prefix=f"rag-eval-adjudication-dispatch:{workflow_run_id}",
                lease_expires_at=occurred_at + timedelta(seconds=90),
                now=occurred_at,
                started_at=occurred_at,
                active_model_ref=_payload_text(
                    workflow_command.payload,
                    "active_model_ref",
                    fallback=WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
                ),
                allow_automatic_fallbacks=True,
                provider_account_refs=_provider_account_refs(workflow_command.payload),
            )
        )
        started_attempts = _started_attempts(prepare_result)
        capacity_retry_at = _optional_datetime_attribute(
            prepare_result,
            "capacity_retry_at",
        )
        if not started_attempts and capacity_retry_at is not None:
            retry_at = (
                capacity_retry_at
                if capacity_retry_at > occurred_at
                else occurred_at + timedelta(seconds=60)
            )
            await workflow_unit_of_work.command_log.reschedule_pending_command(
                command_id=workflow_command.command_id,
                run_after=retry_at,
                rescheduled_at=occurred_at,
            )
            await workflow_unit_of_work.timeline.append_entry(
                _timeline(
                    workflow_command,
                    workflow_run_id,
                    "Adjudication capacity wait",
                    WorkbenchRagEvalWorkflowPhase.ADJUDICATION.value,
                    occurred_at,
                    {"retry_at": retry_at.isoformat()},
                )
            )
            return HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchResult(
                0,
                retry_at,
            )
        if started_attempts:
            await workflow_unit_of_work.outbox.append_event(
                WorkflowEvent(
                    event_id=WorkflowEventId(
                        "workflow-event:"
                        f"{workflow_run_id}:"
                        f"{WorkbenchRagEvalWorkflowEventType.ADJUDICATION_DISPATCH_BATCH_PREPARED.value}:"
                        f"{len(started_attempts)}:{_attempt_text(started_attempts[0], 'attempt_id')}"
                    ),
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.ADJUDICATION_DISPATCH_BATCH_PREPARED.value
                    ),
                    workflow_run_id=workflow_run_id,
                    payload={
                        "workflow_family": "workbench_rag_eval",
                        "workflow_run_id": workflow_run_id,
                        "work_kind": WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND.value,
                        "prepared_dispatch_count": len(started_attempts),
                    },
                    occurred_at=occurred_at,
                    causation_command_id=workflow_command.command_id,
                )
            )
            for attempt in started_attempts:
                await workflow_unit_of_work.outbox.append_event(
                    WorkflowEvent(
                        event_id=WorkflowEventId(
                            "workflow-event:"
                            f"{workflow_run_id}:"
                            f"{WorkbenchRagEvalWorkflowEventType.ADJUDICATION_DISPATCH_ATTEMPT_PREPARED.value}:"
                            f"{_attempt_text(attempt, 'attempt_id')}"
                        ),
                        event_type=(
                            WorkbenchRagEvalWorkflowEventType.ADJUDICATION_DISPATCH_ATTEMPT_PREPARED.value
                        ),
                        workflow_run_id=workflow_run_id,
                        payload={
                            "workflow_family": "workbench_rag_eval",
                            "workflow_run_id": workflow_run_id,
                            "work_kind": WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND.value,
                            "dispatch_attempt_id": _attempt_text(attempt, "attempt_id"),
                            "work_item_id": _attempt_text(attempt, "work_item_id"),
                        },
                        occurred_at=occurred_at,
                        causation_command_id=workflow_command.command_id,
                    )
                )
                await workflow_unit_of_work.command_log.append_pending_command(
                    _execute_command(
                        workflow_command, workflow_run_id, attempt, occurred_at
                    )
                )
        else:
            await workflow_unit_of_work.command_log.append_pending_command(
                _reconcile_command(workflow_command, workflow_run_id, occurred_at)
            )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline(
                workflow_command,
                workflow_run_id,
                "Adjudication dispatch batch prepared",
                WorkbenchRagEvalWorkflowPhase.ADJUDICATION.value,
                occurred_at,
                {"prepared_dispatch_count": len(started_attempts)},
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )
        return HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchResult(
            len(started_attempts),
            None,
        )


def _execute_command(
    source: WorkflowCommand,
    workflow_run_id: str,
    attempt: object,
    occurred_at: datetime,
) -> WorkflowCommand:
    attempt_id = _attempt_text(attempt, "attempt_id")
    command_type = WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION
    key = f"rag-eval:{workflow_run_id}:{command_type.value}:{attempt_id}"
    payload = dict(source.payload)
    payload.update(
        {
            "workflow_run_id": workflow_run_id,
            "dispatch_attempt_id": attempt_id,
            "work_item_id": _attempt_text(attempt, "work_item_id"),
        }
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{key}"),
        command_type=command_type.value,
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _reconcile_command(
    source: WorkflowCommand,
    workflow_run_id: str,
    occurred_at: datetime,
) -> WorkflowCommand:
    command_type = WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS
    key = f"rag-eval:{workflow_run_id}:{command_type.value}:{source.command_id.value}"
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{key}"),
        command_type=command_type.value,
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(key),
        payload=dict(source.payload),
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _timeline(
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    message: str,
    phase: str,
    occurred_at: datetime,
    payload: dict[str, object],
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=f"timeline:{workflow_run_id}:adjudication-prepare:{workflow_command.command_id.value}",
        workflow_run_id=workflow_run_id,
        event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_DISPATCH_BATCH_PREPARED.value,
        phase=phase,
        severity=WorkflowTimelineSeverity.INFO,
        message=message,
        payload_summary=payload,
        occurred_at=occurred_at,
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


def _payload_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"payload.{key} must be positive int")
    return value


def _provider_account_refs(payload: Mapping[str, object]) -> tuple[str, ...]:
    raw = payload.get("capacity_window_provider_account_refs")
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ValueError("capacity_window_provider_account_refs must be sequence")
    return tuple(_non_empty_text(item) for item in raw)


def _started_attempts(result: object) -> tuple[object, ...]:
    attempt_result = getattr(result, "attempt_result", None)
    started_attempts = getattr(attempt_result, "started_attempts", None)
    if not isinstance(started_attempts, tuple):
        raise TypeError("prepare result attempt_result.started_attempts must be tuple")
    return started_attempts


def _optional_datetime_attribute(value: object, attribute_name: str) -> datetime | None:
    attribute = getattr(value, attribute_name, None)
    if attribute is None:
        return None
    if not isinstance(attribute, datetime):
        raise TypeError(f"{attribute_name} must be datetime or None")
    return attribute


def _attempt_text(attempt: object, attribute_name: str) -> str:
    value = getattr(attempt, attribute_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"attempt.{attribute_name} must be non-empty")
    return value


def _non_empty_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty text")
    return value.strip()

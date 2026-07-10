from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from src.contexts.execution_runtime.domain.value_objects.worker_ref import (
    WorkerRef,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
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
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)


class PrepareLlmDispatchBatchPort(Protocol):
    async def execute(
        self,
        command: PrepareLlmDispatchBatchCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchResult:
    workflow_run_id: str
    prepared_dispatch_count: int
    appended_event_count: int
    appended_next_command_count: int
    rescheduled_at: datetime | None
    completed_command_id: WorkflowCommandId | None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_negative_int(
            self.prepared_dispatch_count,
            "prepared_dispatch_count",
        )
        _require_non_negative_int(
            self.appended_event_count,
            "appended_event_count",
        )
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if self.rescheduled_at is not None:
            _require_timezone_aware(self.rescheduled_at, "rescheduled_at")
        if self.completed_command_id is not None and not isinstance(
            self.completed_command_id,
            WorkflowCommandId,
        ):
            raise TypeError("completed_command_id must be WorkflowCommandId when set")
        if self.rescheduled_at is not None and self.completed_command_id is not None:
            raise ValueError("rescheduled command cannot also be reported completed")


class HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler:
    async def execute(
        self,
        command: (HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand),
        *,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)

        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        occurred_at = _execution_occurred_at(workflow_command)
        requested_items = _payload_positive_int(
            workflow_command.payload,
            "scheduled_work_item_count",
        )

        prepare_result = await prepare_llm_dispatch_batch.execute(
            PrepareLlmDispatchBatchCommand(
                work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
                requested_items=requested_items,
                worker=WorkerRef("knowledge-workbench-rag-eval-question-generation"),
                lease_token_prefix=(f"rag-eval-qgen-dispatch:{workflow_run_id}"),
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
            retry_at = _future_retry_at(
                capacity_retry_at,
                occurred_at=occurred_at,
            )
            await workflow_unit_of_work.command_log.reschedule_pending_command(
                command_id=workflow_command.command_id,
                run_after=retry_at,
                rescheduled_at=occurred_at,
            )
            await workflow_unit_of_work.timeline.append_entry(
                _capacity_wait_timeline_entry(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    retry_at=retry_at,
                    occurred_at=occurred_at,
                )
            )
            return HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchResult(
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=0,
                appended_event_count=0,
                appended_next_command_count=0,
                rescheduled_at=retry_at,
                completed_command_id=None,
            )

        appended_event_count = 0
        appended_next_command_count = 0

        if started_attempts:
            await workflow_unit_of_work.outbox.append_event(
                _dispatch_batch_prepared_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    started_attempts=started_attempts,
                    occurred_at=occurred_at,
                )
            )
            appended_event_count += 1

            for attempt in started_attempts:
                await workflow_unit_of_work.outbox.append_event(
                    _dispatch_attempt_prepared_event(
                        workflow_command=workflow_command,
                        workflow_run_id=workflow_run_id,
                        attempt=attempt,
                        occurred_at=occurred_at,
                    )
                )
                appended_event_count += 1

                await workflow_unit_of_work.command_log.append_pending_command(
                    _execute_question_generation_command(
                        source_command=workflow_command,
                        workflow_run_id=workflow_run_id,
                        attempt=attempt,
                        occurred_at=occurred_at,
                    )
                )
                appended_next_command_count += 1
        else:
            await workflow_unit_of_work.command_log.append_pending_command(
                _reconcile_question_generation_command(
                    source_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    occurred_at=occurred_at,
                )
            )
            appended_next_command_count = 1

        await workflow_unit_of_work.timeline.append_entry(
            _prepare_timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                prepared_dispatch_count=len(started_attempts),
                occurred_at=occurred_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchResult(
            workflow_run_id=workflow_run_id,
            prepared_dispatch_count=len(started_attempts),
            appended_event_count=appended_event_count,
            appended_next_command_count=appended_next_command_count,
            rescheduled_at=None,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(
    workflow_command: WorkflowCommand,
) -> None:
    expected = WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
    if workflow_command.command_type != expected:
        raise ValueError(
            "workflow_command command_type must be "
            "PrepareRagEvalQuestionGenerationDispatchBatch"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _execution_occurred_at(
    workflow_command: WorkflowCommand,
) -> datetime:
    now = datetime.now(timezone.utc)
    return max(now, workflow_command.updated_at)


def _future_retry_at(
    retry_at: datetime,
    *,
    occurred_at: datetime,
) -> datetime:
    _require_timezone_aware(retry_at, "retry_at")
    if retry_at > occurred_at:
        return retry_at
    return occurred_at + timedelta(seconds=60)


def _provider_account_refs(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    raw = payload.get("capacity_window_provider_account_refs")
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ValueError("capacity_window_provider_account_refs must be a sequence")
    refs: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                "capacity_window_provider_account_refs must contain non-empty strings"
            )
        refs.append(item)
    return tuple(refs)


def _started_attempts(result: object) -> tuple[object, ...]:
    attempt_result = getattr(result, "attempt_result", None)
    started_attempts = getattr(
        attempt_result,
        "started_attempts",
        None,
    )
    if not isinstance(started_attempts, tuple):
        raise TypeError("prepare result attempt_result.started_attempts must be tuple")
    return started_attempts


def _optional_datetime_attribute(
    value: object,
    attribute_name: str,
) -> datetime | None:
    attribute = getattr(value, attribute_name, None)
    if attribute is None:
        return None
    _require_timezone_aware(attribute, attribute_name)
    return attribute


def _dispatch_batch_prepared_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    started_attempts: tuple[object, ...],
    occurred_at: datetime,
) -> WorkflowEvent:
    attempt_ids = tuple(
        _attempt_text(attempt, "attempt_id") for attempt in started_attempts
    )
    batch_key = f"{len(attempt_ids)}:{attempt_ids[0]}"
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_DISPATCH_BATCH_PREPARED.value}:"
            f"{batch_key}"
        ),
        event_type=(
            WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_DISPATCH_BATCH_PREPARED.value
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
            "prepared_dispatch_count": len(attempt_ids),
            "dispatch_attempt_ids": attempt_ids,
            "work_item_ids": tuple(
                _attempt_text(attempt, "work_item_id") for attempt in started_attempts
            ),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _dispatch_attempt_prepared_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    attempt: object,
    occurred_at: datetime,
) -> WorkflowEvent:
    attempt_id = _attempt_text(attempt, "attempt_id")
    dispatch_payload = _attempt_mapping(
        attempt,
        "dispatch_payload",
    )
    allocation = dispatch_payload.get("llm_allocation")
    if not isinstance(allocation, Mapping):
        raise ValueError(
            "started attempt dispatch_payload.llm_allocation must be mapping"
        )

    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{workflow_run_id}:"
            f"{WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_DISPATCH_ATTEMPT_PREPARED.value}:"
            f"{attempt_id}"
        ),
        event_type=(
            WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_DISPATCH_ATTEMPT_PREPARED.value
        ),
        workflow_run_id=workflow_run_id,
        payload={
            "workflow_family": "workbench_rag_eval",
            "workflow_run_id": workflow_run_id,
            "project_id": _payload_text(
                workflow_command.payload,
                "project_id",
            ),
            "dispatch_attempt_id": attempt_id,
            "work_item_id": _attempt_text(attempt, "work_item_id"),
            "attempt_number": _attempt_positive_int(
                attempt,
                "attempt_number",
            ),
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
            "provider": _mapping_text(allocation, "provider"),
            "account_ref": _mapping_text(allocation, "account_ref"),
            "model_ref": _mapping_text(allocation, "model_ref"),
        },
        occurred_at=occurred_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.idempotency_key.value,
    )


def _execute_question_generation_command(
    *,
    source_command: WorkflowCommand,
    workflow_run_id: str,
    attempt: object,
    occurred_at: datetime,
) -> WorkflowCommand:
    attempt_id = _attempt_text(attempt, "attempt_id")
    work_item_id = _attempt_text(attempt, "work_item_id")
    idempotency_key = (
        f"execute-rag-eval-question-generation:{workflow_run_id}:{attempt_id}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION.value
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
            "dispatch_attempt_id": attempt_id,
            "work_item_id": work_item_id,
            "question_generation_prepare_command_id": (source_command.command_id.value),
            "question_generation_prepare_idempotency_key": (
                source_command.idempotency_key.value
            ),
            "current_phase": (WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION.value),
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _reconcile_question_generation_command(
    *,
    source_command: WorkflowCommand,
    workflow_run_id: str,
    occurred_at: datetime,
) -> WorkflowCommand:
    idempotency_key = (
        f"reconcile-rag-eval-question-generation:"
        f"{workflow_run_id}:after-zero-prepare:"
        f"{source_command.command_id.value}"
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
            "trigger": "zero_prepare_without_capacity_retry",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _capacity_wait_timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    retry_at: datetime,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            "RagEvalQuestionGenerationCapacityWaiting:"
            f"{workflow_command.command_id.value}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=workflow_command.command_type,
        phase=WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION.value,
        severity=WorkflowTimelineSeverity.INFO,
        message=("RAG Eval question generation is waiting for LLM capacity"),
        payload_summary={
            "workflow_family": "workbench_rag_eval",
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
            "capacity_retry_at": retry_at.isoformat(),
            "waiting_capacity": True,
        },
        occurred_at=occurred_at,
        source_ref=(WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
    )


def _prepare_timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    prepared_dispatch_count: int,
    occurred_at: datetime,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            "RagEvalQuestionGenerationDispatchBatchPrepared:"
            f"{workflow_command.command_id.value}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=(
            WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_DISPATCH_BATCH_PREPARED.value
        ),
        phase=WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION.value,
        severity=WorkflowTimelineSeverity.INFO,
        message="RAG Eval question-generation dispatch batch prepared",
        payload_summary={
            "workflow_family": "workbench_rag_eval",
            "prepared_dispatch_count": prepared_dispatch_count,
            "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
        },
        occurred_at=occurred_at,
        source_ref=(WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
    )


def _attempt_text(attempt: object, field_name: str) -> str:
    value = getattr(attempt, field_name, None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"started attempt {field_name} must be non-empty")
    return value


def _attempt_positive_int(
    attempt: object,
    field_name: str,
) -> int:
    value = getattr(attempt, field_name, None)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"started attempt {field_name} must be positive int")
    return value


def _attempt_mapping(
    attempt: object,
    field_name: str,
) -> Mapping[str, object]:
    value = getattr(attempt, field_name, None)
    if not isinstance(value, Mapping):
        raise ValueError(f"started attempt {field_name} must be mapping")
    return value


def _mapping_text(
    mapping: Mapping[str, object],
    key: str,
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"mapping must include non-empty {key}")
    return value


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


def _payload_positive_int(
    payload: Mapping[str, object],
    key: str,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"workflow command payload must include positive int {key}")
    return value


def _require_non_empty_text(
    value: str,
    field_name: str,
) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(
    value: int,
    field_name: str,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_timezone_aware(
    value: datetime,
    field_name: str,
) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")

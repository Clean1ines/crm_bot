from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
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
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEvalPostPromotionVerificationCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEvalPostPromotionVerificationResult:
    workflow_run_id: str
    revision_id: str
    runtime_entry_id: str
    batch_key: str
    batch_limit: int
    processed_count: int
    remaining_count: int
    total_query_count: int
    terminal: bool
    status: str
    decision: str | None = None
    failure_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "workflow_run_id",
            "revision_id",
            "runtime_entry_id",
            "batch_key",
            "status",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        for field_name in (
            "batch_limit",
            "processed_count",
            "remaining_count",
            "total_query_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.batch_limit <= 0:
            raise ValueError("batch_limit must be positive")
        if not isinstance(self.terminal, bool):
            raise TypeError("terminal must be bool")
        if self.decision is not None and (
            not isinstance(self.decision, str) or not self.decision.strip()
        ):
            raise ValueError("decision must be non-empty when provided")
        for reason in self.failure_reasons:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("failure_reasons must contain non-empty strings")


class RunWorkbenchRagEvalPostPromotionVerificationPort(Protocol):
    async def execute(
        self,
        command: RunWorkbenchRagEvalPostPromotionVerificationCommand,
    ) -> RunWorkbenchRagEvalPostPromotionVerificationResult: ...


@dataclass(frozen=True, slots=True)
class HandleRunWorkbenchRagEvalPostPromotionVerificationCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


class HandleRunWorkbenchRagEvalPostPromotionVerificationCommandHandler:
    async def execute(
        self,
        command: HandleRunWorkbenchRagEvalPostPromotionVerificationCommand,
        *,
        post_promotion_verification_executor: (
            RunWorkbenchRagEvalPostPromotionVerificationPort
        ),
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> RunWorkbenchRagEvalPostPromotionVerificationResult:
        result = await post_promotion_verification_executor.execute(
            RunWorkbenchRagEvalPostPromotionVerificationCommand(
                workflow_command=command.workflow_command,
            )
        )
        payload = _event_payload(
            workflow_command=command.workflow_command,
            result=result,
        )
        persisted_batch_event = await workflow_unit_of_work.outbox.append_event(
            _event(
                workflow_command=command.workflow_command,
                event_type=(
                    WorkbenchRagEvalWorkflowEventType.VERIFICATION_BATCH_COMPLETED.value
                ),
                suffix="verification-batch-completed",
                payload=payload,
            )
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(persisted_batch_event)

        if result.remaining_count > 0:
            await workflow_unit_of_work.command_log.append_pending_command(
                _continuation_command(
                    workflow_command=command.workflow_command,
                    result=result,
                    batch_event=persisted_batch_event,
                )
            )
        else:
            persisted_terminal_event = await workflow_unit_of_work.outbox.append_event(
                _event(
                    workflow_command=command.workflow_command,
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.VERIFICATION_COMPLETED.value
                    ),
                    suffix="verification-completed",
                    payload=payload,
                )
            )
            if frontend_event_projection_writer is not None:
                await frontend_event_projection_writer.execute(persisted_terminal_event)

        await workflow_unit_of_work.progress_snapshots.save_snapshot(
            WorkflowProgressSnapshot(
                workflow_run_id=result.workflow_run_id,
                current_phase=(
                    WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION.value
                ),
                workflow_status="verifying"
                if result.remaining_count > 0
                else "completed",
                total_work_items=result.total_query_count,
                completed_work_items=result.total_query_count - result.remaining_count,
                domain_counters={
                    "rag_eval_verification_processed_queries": (
                        result.total_query_count - result.remaining_count
                    ),
                    "rag_eval_verification_remaining_queries": result.remaining_count,
                    "rag_eval_verification_batch_limit": result.batch_limit,
                },
                updated_at=command.workflow_command.updated_at,
            )
        )
        if result.remaining_count == 0:
            await workflow_unit_of_work.timeline.append_entry(
                WorkflowTimelineEntry(
                    timeline_entry_id=(
                        "workflow-timeline:"
                        + _stable_hash(
                            command.workflow_command.command_id.value,
                            "verification-completed",
                        )
                    ),
                    workflow_run_id=result.workflow_run_id,
                    event_type=(
                        WorkbenchRagEvalWorkflowEventType.VERIFICATION_COMPLETED.value
                    ),
                    phase=WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION.value,
                    severity=WorkflowTimelineSeverity.INFO,
                    message="RAG Eval post-promotion verification completed",
                    payload_summary=payload,
                    occurred_at=command.workflow_command.updated_at,
                )
            )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=command.workflow_command.command_id,
            completed_at=command.workflow_command.updated_at,
        )
        return result


def _event(
    *,
    workflow_command: WorkflowCommand,
    event_type: str,
    suffix: str,
    payload: dict[str, object],
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            + _stable_hash(workflow_command.command_id.value, event_type, suffix)
        ),
        event_type=event_type,
        workflow_run_id=workflow_command.workflow_run_id,
        payload=payload,
        occurred_at=workflow_command.updated_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.correlation_id,
    )


def _event_payload(
    *,
    workflow_command: WorkflowCommand,
    result: RunWorkbenchRagEvalPostPromotionVerificationResult,
) -> dict[str, object]:
    payload = workflow_command.payload
    return {
        "workflow_run_id": result.workflow_run_id,
        "rag_eval_run_id": result.workflow_run_id,
        "run_id": result.workflow_run_id,
        "project_id": _payload_text(payload, "project_id"),
        "revision_id": _payload_text(payload, "revision_id"),
        "runtime_entry_id": _payload_text(payload, "runtime_entry_id"),
        "phase": WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION.value,
        "status": result.status,
        "batch_key": result.batch_key,
        "batch_limit": result.batch_limit,
        "processed_count": result.processed_count,
        "remaining_count": result.remaining_count,
        "total_query_count": result.total_query_count,
        "succeeded_count": result.processed_count,
        "failed_count": 0,
        "decision": result.decision,
        "failure_reasons": list(result.failure_reasons),
    }


def _continuation_command(
    *,
    workflow_command: WorkflowCommand,
    result: RunWorkbenchRagEvalPostPromotionVerificationResult,
    batch_event: WorkflowEvent,
) -> WorkflowCommand:
    next_batch_index = _payload_int(workflow_command.payload, "batch_index", 0) + 1
    idempotency_key = (
        "rag-eval-post-promotion-verification:"
        f"{result.revision_id}:batch:{next_batch_index}"
    )
    payload = dict(workflow_command.payload)
    payload.update(
        {
            "batch_index": next_batch_index,
            "batch_limit": result.batch_limit,
            "batch_key": f"{result.revision_id}:batch:{next_batch_index}",
            "verification_cursor": (
                f"{result.revision_id}:"
                f"{result.total_query_count - result.remaining_count}"
            ),
        }
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=workflow_command.command_type,
        workflow_run_id=workflow_command.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=workflow_command.updated_at,
        created_at=workflow_command.updated_at,
        updated_at=workflow_command.updated_at,
        causation_event_id=batch_event.event_id,
        correlation_id=workflow_command.correlation_id
        or workflow_command.command_id.value,
    )


def _stable_hash(*parts: str) -> str:
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _payload_text(payload: object, key: str) -> str:
    if not isinstance(payload, Mapping):
        raise TypeError("workflow command payload must be mapping")
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload.{key} must be non-empty")
    return value.strip()


def _payload_int(payload: object, key: str, default: int) -> int:
    if not isinstance(payload, Mapping):
        raise TypeError("workflow command payload must be mapping")
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"workflow command payload.{key} must be int")
    if value < 0:
        raise ValueError(f"workflow command payload.{key} must be non-negative")
    return value

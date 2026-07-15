from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_adjudication_work import (
    WorkbenchRagEvalAdjudicationEligibilityPolicy,
    WorkbenchRagEvalAdjudicationWorkPlanner,
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
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


@dataclass(frozen=True, slots=True)
class HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleScheduleWorkbenchRagEvalAdjudicationWorkResult:
    eligible_count: int
    scheduled_count: int
    zero_eligible_fast_path: bool


class HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler:
    async def execute(
        self,
        command: HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand,
        *,
        rag_eval_repository: WorkbenchRagEvalRepositoryPort,
        work_item_scheduling_repository: WorkItemSchedulingRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        provider_messages_builder: object,
        adjudication_model_profile: ModelProfile,
    ) -> HandleScheduleWorkbenchRagEvalAdjudicationWorkResult:
        current = command.workflow_command
        if (
            current.command_type
            != WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK.value
            or current.status is not WorkflowCommandStatus.PENDING
        ):
            raise ValueError("workflow command must be pending adjudication scheduling")
        run_id = _payload_text(current, "workflow_run_id")
        rag_eval_run_id = _payload_text(current, "rag_eval_run_id", fallback=run_id)
        project_id = _payload_text(current, "project_id")
        if run_id != current.workflow_run_id or rag_eval_run_id != run_id:
            raise ValueError("workflow and RAG Eval run ids must match")
        now = current.updated_at
        inputs = await rag_eval_repository.list_adjudication_planning_inputs(
            run_id=run_id,
            project_id=project_id,
        )
        eligibility_policy = WorkbenchRagEvalAdjudicationEligibilityPolicy()
        eligible = tuple(
            item
            for item in inputs
            if eligibility_policy.is_eligible(
                evaluation_role=item.evaluation_role,
                promotion_eligible=item.promotion_eligible,
                ambiguity_risk=item.ambiguity_risk,
                classification=item.classification,
            )
        )
        if not eligible:
            await rag_eval_repository.create_promotion_candidates_from_adjudications(
                run_id=run_id,
                project_id=project_id,
                created_at=now,
                pass_weak_enabled=eligibility_policy.pass_weak_enabled,
            )
            await _append_candidates_ready(
                workflow_unit_of_work=workflow_unit_of_work,
                current=current,
                run_id=run_id,
                project_id=project_id,
                candidate_count=0,
                now=now,
                zero_eligible_fast_path=True,
            )
            await workflow_unit_of_work.command_log.mark_command_completed(
                command_id=current.command_id,
                completed_at=now,
            )
            return HandleScheduleWorkbenchRagEvalAdjudicationWorkResult(0, 0, True)

        provider_messages_by_question_id = {
            item.question_id: tuple(
                provider_messages_builder.provider_messages(item)  # type: ignore[attr-defined]
            )
            for item in eligible
        }
        plans = WorkbenchRagEvalAdjudicationWorkPlanner(
            adjudication_model_profile=adjudication_model_profile,
        ).plan(
            inputs=eligible,
            provider_messages_by_question_id=provider_messages_by_question_id,
        )
        schedule = await EnsureWorkItemsScheduled(
            repository=work_item_scheduling_repository
        ).execute(EnsureWorkItemsScheduledCommand(plans=plans))
        if schedule.conflict_count:
            raise ValueError("adjudication work item idempotency conflict")
        await rag_eval_repository.transition_run_progress(
            run_id=run_id,
            project_id=project_id,
            status=WorkbenchRagEvalRunStatus.RUNNING,
            current_phase=WorkbenchRagEvalCurrentPhase.ADJUDICATION,
            progress=WorkbenchRagEvalRunProgress(
                adjudication_total=len(plans),
                adjudication_waiting=len(plans),
            ),
            updated_at=now,
        )
        await workflow_unit_of_work.command_log.append_pending_command(
            _prepare_command(current, run_id, project_id, len(plans), now)
        )
        await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{run_id}:adjudication-work-scheduled:{current.command_id.value}"
                ),
                event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_WORK_SCHEDULED.value,
                workflow_run_id=run_id,
                payload={
                    "workflow_run_id": run_id,
                    "project_id": project_id,
                    "eligible_count": len(plans),
                    "created_count": schedule.created_count,
                    "already_exists_count": schedule.already_exists_count,
                },
                occurred_at=now,
                causation_command_id=current.command_id,
            )
        )
        await workflow_unit_of_work.progress_snapshots.save_snapshot(
            WorkflowProgressSnapshot(
                workflow_run_id=run_id,
                current_phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION.value,
                workflow_status="RUNNING",
                total_work_items=len(plans),
                scheduled_work_items=len(plans),
                running_work_items=0,
                completed_work_items=0,
                deferred_work_items=0,
                retryable_failed_work_items=0,
                terminal_failed_work_items=0,
                blocked_work_items=0,
                updated_at=now,
            )
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=f"timeline:{run_id}:adjudication-work-scheduled:{current.command_id.value}",
                workflow_run_id=run_id,
                event_type=WorkbenchRagEvalWorkflowEventType.ADJUDICATION_WORK_SCHEDULED.value,
                phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="RAG Eval adjudication work scheduled",
                payload_summary={"eligible_count": len(plans)},
                occurred_at=now,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=current.command_id,
            completed_at=now,
        )
        return HandleScheduleWorkbenchRagEvalAdjudicationWorkResult(
            len(eligible),
            len(plans),
            False,
        )


def _prepare_command(
    current: WorkflowCommand,
    run_id: str,
    project_id: str,
    scheduled_count: int,
    now: datetime,
) -> WorkflowCommand:
    command_type = (
        WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH
    )
    key = f"rag-eval:{run_id}:{command_type.value}:initial"
    payload = dict(current.payload)
    payload.update(
        {
            "workflow_run_id": run_id,
            "rag_eval_run_id": run_id,
            "project_id": project_id,
            "scheduled_work_item_count": scheduled_count,
        }
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{key}"),
        command_type=command_type.value,
        workflow_run_id=run_id,
        idempotency_key=WorkflowIdempotencyKey(key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=now,
        created_at=now,
        updated_at=now,
    )


async def _append_candidates_ready(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    current: WorkflowCommand,
    run_id: str,
    project_id: str,
    candidate_count: int,
    now: datetime,
    zero_eligible_fast_path: bool,
) -> None:
    payload = {
        "workflow_run_id": run_id,
        "project_id": project_id,
        "candidate_count": candidate_count,
        "zero_eligible_fast_path": zero_eligible_fast_path,
    }
    await workflow_unit_of_work.outbox.append_event(
        WorkflowEvent(
            event_id=WorkflowEventId(
                f"workflow-event:{run_id}:promotion-candidates-ready:{current.command_id.value}"
            ),
            event_type=WorkbenchRagEvalWorkflowEventType.PROMOTION_CANDIDATES_READY.value,
            workflow_run_id=run_id,
            payload=payload,
            occurred_at=now,
            causation_command_id=current.command_id,
        )
    )
    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=run_id,
            current_phase=WorkbenchRagEvalWorkflowPhase.PROMOTION_REVIEW.value,
            workflow_status="PROMOTION_REVIEW",
            total_work_items=0,
            scheduled_work_items=0,
            running_work_items=0,
            completed_work_items=0,
            deferred_work_items=0,
            retryable_failed_work_items=0,
            terminal_failed_work_items=0,
            blocked_work_items=0,
            updated_at=now,
        )
    )
    await workflow_unit_of_work.timeline.append_entry(
        WorkflowTimelineEntry(
            timeline_entry_id=f"timeline:{run_id}:promotion-candidates-ready:{current.command_id.value}",
            workflow_run_id=run_id,
            event_type=WorkbenchRagEvalWorkflowEventType.PROMOTION_CANDIDATES_READY.value,
            phase=WorkbenchRagEvalWorkflowPhase.PROMOTION_REVIEW.value,
            severity=WorkflowTimelineSeverity.INFO,
            message="RAG Eval promotion candidates ready",
            payload_summary=payload,
            occurred_at=now,
        )
    )


def _payload_text(
    current: WorkflowCommand,
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = current.payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload.{key} must be non-empty")
    return value.strip()

from __future__ import annotations

from dataclasses import dataclass, replace

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.open_draft_claim_curation_workspace import (
    OpenDraftClaimCurationWorkspace,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
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
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)


@dataclass(frozen=True, slots=True)
class HandleOpenDraftClaimCurationWorkspaceCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleOpenDraftClaimCurationWorkspaceResult:
    workflow_run_id: str
    workspace_ref: str
    item_count: int


@dataclass(frozen=True, slots=True)
class HandleOpenDraftClaimCurationWorkspaceCommandHandler:
    async def execute(
        self,
        command: HandleOpenDraftClaimCurationWorkspaceCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        workflow_state_repository: KnowledgeExtractionSagaStateRepositoryPort,
        curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort,
        compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort
        ),
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> HandleOpenDraftClaimCurationWorkspaceResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE.value
        ):
            raise ValueError(
                "workflow_command command_type must be OpenDraftClaimCurationWorkspace"
            )
        if workflow_command.status is not WorkflowCommandStatus.PENDING:
            raise ValueError("workflow_command status must be PENDING")

        state = await workflow_state_repository.load_workflow_state(
            workflow_command.workflow_run_id
        )
        if state is None:
            raise LookupError("knowledge extraction workflow state not found")

        snapshot = await OpenDraftClaimCurationWorkspace(
            curation_workspace_repository=curation_workspace_repository,
            compaction_reduction_state_repository=(
                compaction_reduction_state_repository
            ),
        ).execute(
            workflow_run_id=workflow_command.workflow_run_id,
            project_id=state.project_id,
            source_document_ref=state.source_document_ref,
            created_at=workflow_command.updated_at,
        )

        opened_event = await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{workflow_command.workflow_run_id}:"
                    f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_OPENED.value}:"
                    f"{workflow_command.command_id.value}"
                ),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_OPENED.value
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                payload={
                    "project_id": state.project_id,
                    "source_document_ref": state.source_document_ref,
                    "workspace_ref": snapshot.workspace.workspace_ref,
                    "item_count": len(snapshot.items),
                },
                occurred_at=workflow_command.updated_at,
                causation_command_id=workflow_command.command_id,
                correlation_id=workflow_command.command_id.value,
            )
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(opened_event)
        review_required_event = await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{workflow_command.workflow_run_id}:"
                    f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value}:"
                    f"{workflow_command.command_id.value}"
                ),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                payload={
                    "project_id": state.project_id,
                    "source_document_ref": state.source_document_ref,
                    "workspace_ref": snapshot.workspace.workspace_ref,
                    "item_count": len(snapshot.items),
                },
                occurred_at=workflow_command.updated_at,
                causation_command_id=workflow_command.command_id,
                correlation_id=workflow_command.command_id.value,
            )
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(review_required_event)
        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_command=workflow_command,
            item_count=len(snapshot.items),
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{workflow_command.workflow_run_id}:"
                    f"DraftClaimCurationReviewRequired:{workflow_command.command_id.value}"
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_REVIEW_REQUIRED.value
                ),
                phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CURATION.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="Draft claim curation workspace is ready for review",
                payload_summary={
                    "workspace_ref": snapshot.workspace.workspace_ref,
                    "item_count": len(snapshot.items),
                },
                occurred_at=workflow_command.updated_at,
                source_ref=workflow_command.command_type,
            )
        )
        await workflow_state_repository.save_workflow_state(
            replace(
                state,
                status=KnowledgeExtractionWorkflowStatus.WAITING_FOR_REVIEW,
                current_phase=KnowledgeExtractionPhaseKey.WAITING_FOR_REVIEW,
                review_status="pending",
                updated_at=workflow_command.updated_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=workflow_command.updated_at,
        )
        return HandleOpenDraftClaimCurationWorkspaceResult(
            workflow_run_id=workflow_command.workflow_run_id,
            workspace_ref=snapshot.workspace.workspace_ref,
            item_count=len(snapshot.items),
        )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_command: WorkflowCommand,
    item_count: int,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_command.workflow_run_id
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["draft_claim_curation_item_count"] = item_count
    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_command.workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CURATION.value,
            workflow_status=KnowledgeExtractionWorkflowStatus.WAITING_FOR_REVIEW.value,
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
            running_work_items=0,
            completed_work_items=(
                existing.completed_work_items if existing is not None else 0
            ),
            deferred_work_items=(
                existing.deferred_work_items if existing is not None else 0
            ),
            retryable_failed_work_items=(
                existing.retryable_failed_work_items if existing is not None else 0
            ),
            terminal_failed_work_items=(
                existing.terminal_failed_work_items if existing is not None else 0
            ),
            blocked_work_items=0,
            domain_counters=domain_counters,
            started_at=(
                existing.started_at
                if existing is not None
                else workflow_command.updated_at
            ),
            updated_at=workflow_command.updated_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )

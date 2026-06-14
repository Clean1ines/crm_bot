from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_cluster_preview_repository_port import (
    DraftClaimClusterPreviewRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.build_draft_claim_cluster_preview import (
    BuildDraftClaimClusterPreview,
    DraftClaimCompactionPreviewReadRepositoryPort,
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


@dataclass(frozen=True, slots=True)
class HandleBuildClusterPreviewCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleBuildClusterPreviewResult:
    workflow_run_id: str
    claim_count: int
    group_count: int


@dataclass(frozen=True, slots=True)
class HandleBuildClusterPreviewCommandHandler:
    async def execute(
        self,
        command: HandleBuildClusterPreviewCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        compaction_reduction_state_repository: DraftClaimCompactionPreviewReadRepositoryPort,
        cluster_preview_repository: DraftClaimClusterPreviewRepositoryPort,
    ) -> HandleBuildClusterPreviewResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != KnowledgeExtractionCanonicalCommandType.BUILD_CLUSTER_PREVIEW.value
        ):
            raise ValueError(
                "workflow_command command_type must be BuildClusterPreview"
            )
        if workflow_command.status is not WorkflowCommandStatus.PENDING:
            raise ValueError("workflow_command status must be PENDING")

        build_result = await BuildDraftClaimClusterPreview(
            compaction_reduction_state_repository=(
                compaction_reduction_state_repository
            ),
            cluster_preview_repository=cluster_preview_repository,
        ).execute(
            workflow_run_id=workflow_command.workflow_run_id,
            created_at=workflow_command.updated_at,
        )

        await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{workflow_command.workflow_run_id}:"
                    f"{KnowledgeExtractionCanonicalEventType.CLUSTER_PREVIEW_READY.value}:"
                    f"{workflow_command.command_id.value}"
                ),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.CLUSTER_PREVIEW_READY.value
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                payload={
                    "workflow_run_id": workflow_command.workflow_run_id,
                    "claim_count": build_result.claim_count,
                    "group_count": build_result.group_count,
                },
                occurred_at=workflow_command.updated_at,
                causation_command_id=workflow_command.command_id,
                correlation_id=workflow_command.command_id.value,
            )
        )
        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_command=workflow_command,
            claim_count=build_result.claim_count,
            group_count=build_result.group_count,
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{workflow_command.workflow_run_id}:"
                    f"ClusterPreviewReady:{workflow_command.command_id.value}"
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.CLUSTER_PREVIEW_READY.value
                ),
                phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="Draft claim cluster preview ready",
                payload_summary={
                    "claim_count": build_result.claim_count,
                    "group_count": build_result.group_count,
                },
                occurred_at=workflow_command.updated_at,
                source_ref=workflow_command.command_type,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=workflow_command.updated_at,
        )

        return HandleBuildClusterPreviewResult(
            workflow_run_id=workflow_command.workflow_run_id,
            claim_count=build_result.claim_count,
            group_count=build_result.group_count,
        )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_command: WorkflowCommand,
    claim_count: int,
    group_count: int,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_command.workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters.update(
        {
            "draft_claim_cluster_preview_claim_count": claim_count,
            "draft_claim_cluster_preview_group_count": group_count,
        }
    )
    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_command.workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            workflow_status="RUNNING",
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
            started_at=existing.started_at
            if existing is not None
            else workflow_command.updated_at,
            updated_at=workflow_command.updated_at,
            completed_at=existing.completed_at if existing is not None else None,
        )
    )

from __future__ import annotations

from dataclasses import dataclass, replace

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
)
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
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_publication_repository_port import (
    DraftClaimCurationPublicationRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.publish_draft_claim_curation_workspace import (
    PublishDraftClaimCurationWorkspace,
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
class HandlePublishDraftClaimCurationWorkspaceCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandlePublishDraftClaimCurationWorkspaceResult:
    workflow_run_id: str
    publication_id: str
    published_item_count: int


@dataclass(frozen=True, slots=True)
class HandlePublishDraftClaimCurationWorkspaceCommandHandler:
    async def execute(
        self,
        command: HandlePublishDraftClaimCurationWorkspaceCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        workflow_state_repository: KnowledgeExtractionSagaStateRepositoryPort,
        curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort,
        curation_publication_repository: DraftClaimCurationPublicationRepositoryPort,
        embedding_generation_port: EmbeddingGenerationPort,
        embedding_model_id: str,
        embedding_dimensions: int,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> HandlePublishDraftClaimCurationWorkspaceResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != KnowledgeExtractionCanonicalCommandType.PUBLISH_DRAFT_CLAIM_CURATION_WORKSPACE.value
        ):
            raise ValueError(
                "workflow_command command_type must be PublishDraftClaimCurationWorkspace"
            )
        if workflow_command.status is not WorkflowCommandStatus.PENDING:
            raise ValueError("workflow_command status must be PENDING")

        state = await workflow_state_repository.load_workflow_state(
            workflow_command.workflow_run_id
        )
        if state is None:
            raise LookupError("knowledge extraction workflow state not found")

        result = await PublishDraftClaimCurationWorkspace(
            curation_workspace_repository=curation_workspace_repository,
            curation_publication_repository=curation_publication_repository,
            embedding_generation_port=embedding_generation_port,
            embedding_model_id=embedding_model_id,
            embedding_dimensions=embedding_dimensions,
        ).execute(
            workflow_run_id=workflow_command.workflow_run_id,
            published_at=workflow_command.updated_at,
        )
        published_event = await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{workflow_command.workflow_run_id}:"
                    f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value}:"
                    f"{workflow_command.command_id.value}"
                ),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                payload={
                    "project_id": state.project_id,
                    "source_document_ref": state.source_document_ref,
                    "publication_id": result.publication_id,
                    "published_item_count": result.published_item_count,
                    "runtime_entry_count": result.runtime_entry_count,
                    "embedding_count": result.embedding_count,
                },
                occurred_at=workflow_command.updated_at,
                causation_command_id=workflow_command.command_id,
                correlation_id=workflow_command.command_id.value,
            )
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(published_event)
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{workflow_command.workflow_run_id}:"
                    f"DraftClaimCurationWorkspacePublished:{workflow_command.command_id.value}"
                ),
                workflow_run_id=workflow_command.workflow_run_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CURATION_WORKSPACE_PUBLISHED.value
                ),
                phase=KnowledgeExtractionCanonicalPhase.PUBLICATION.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="Curated claims published to the runtime retrieval surface",
                payload_summary={
                    "publication_id": result.publication_id,
                    "published_item_count": result.published_item_count,
                    "embedding_count": result.embedding_count,
                },
                occurred_at=workflow_command.updated_at,
                source_ref=workflow_command.command_type,
            )
        )
        await _save_completed_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_command=workflow_command,
            published_item_count=result.published_item_count,
            embedding_count=result.embedding_count,
        )
        await workflow_state_repository.save_workflow_state(
            replace(
                state,
                status=KnowledgeExtractionWorkflowStatus.COMPLETED,
                current_phase=KnowledgeExtractionPhaseKey.DONE,
                review_status="completed",
                publication_ref=result.publication_id,
                updated_at=workflow_command.updated_at,
                completed_at=workflow_command.updated_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=workflow_command.updated_at,
        )
        return HandlePublishDraftClaimCurationWorkspaceResult(
            workflow_run_id=workflow_command.workflow_run_id,
            publication_id=result.publication_id,
            published_item_count=result.published_item_count,
        )


async def _save_completed_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_command: WorkflowCommand,
    published_item_count: int,
    embedding_count: int,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_command.workflow_run_id
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters.update(
        {
            "published_canonical_knowledge_entry_count": published_item_count,
            "published_retrieval_embedding_count": embedding_count,
        }
    )
    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_command.workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.COMPLETED.value,
            workflow_status=KnowledgeExtractionWorkflowStatus.COMPLETED.value,
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
            completed_at=workflow_command.updated_at,
        )
    )

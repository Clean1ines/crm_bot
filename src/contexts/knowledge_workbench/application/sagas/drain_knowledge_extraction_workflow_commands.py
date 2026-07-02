from __future__ import annotations

from dataclasses import dataclass
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_persistence_port import (
    DraftClaimEmbeddingPersistencePort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_read_repository_port import (
    DraftClaimEmbeddingReadRepositoryPort,
)

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_builder_retry_action_read_repository_port import (
    ClaimBuilderRetryActionReadRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_split_supersede_repository_port import (
    WorkItemSplitSupersedeRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_publication_repository_port import (
    DraftClaimCurationPublicationRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.dispatch_knowledge_extraction_workflow_command import (
    DispatchKnowledgeExtractionWorkflowCommand,
    DispatchKnowledgeExtractionWorkflowCommandHandler,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    ExecutePreparedLlmDispatchAttemptPort,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    PrepareLlmDispatchBatchPort,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)


WORKFLOW_MANUALLY_PAUSED = "WORKFLOW_MANUALLY_PAUSED"
WORKFLOW_CLEANUP_IN_PROGRESS = "WORKFLOW_CLEANUP_IN_PROGRESS"
WORKFLOW_CANCELLED = "WORKFLOW_CANCELLED"


@dataclass(frozen=True, slots=True)
class DrainKnowledgeExtractionWorkflowCommandsCommand:
    workflow_run_id: str
    max_commands: int = 10

    def __post_init__(self) -> None:
        if (
            not isinstance(self.workflow_run_id, str)
            or not self.workflow_run_id.strip()
        ):
            raise ValueError("workflow_run_id must be non-empty")
        if not isinstance(self.max_commands, int):
            raise TypeError("max_commands must be int")
        if self.max_commands <= 0:
            raise ValueError("max_commands must be > 0")


@dataclass(frozen=True, slots=True)
class DrainKnowledgeExtractionWorkflowCommandsResult:
    workflow_run_id: str
    inspected_count: int
    dispatched_count: int
    blocked_count: int
    last_blocked_command_type: str | None
    last_blocked_reason: str | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.workflow_run_id, str)
            or not self.workflow_run_id.strip()
        ):
            raise ValueError("workflow_run_id must be non-empty")
        for field_name, value in (
            ("inspected_count", self.inspected_count),
            ("dispatched_count", self.dispatched_count),
            ("blocked_count", self.blocked_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if self.blocked_count == 0:
            if self.last_blocked_command_type is not None:
                raise ValueError(
                    "unblocked drain cannot have last_blocked_command_type"
                )
            if self.last_blocked_reason is not None:
                raise ValueError("unblocked drain cannot have last_blocked_reason")


class DrainKnowledgeExtractionWorkflowCommands:
    async def execute(
        self,
        command: DrainKnowledgeExtractionWorkflowCommandsCommand,
        *,
        source_unit_repository: SourceManagementRepositoryPort,
        knowledge_unit_of_work: WorkItemSchedulingRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort | None = None,
        execute_prepared_llm_dispatch_attempt: (
            ExecutePreparedLlmDispatchAttemptPort | None
        ) = None,
        capacity_observation_repository: (
            LlmAttemptCapacityObservationRepositoryPort | None
        ) = None,
        work_item_progress_read_repository: (
            WorkItemProgressReadRepositoryPort | None
        ) = None,
        claim_builder_retry_action_read_repository: (
            ClaimBuilderRetryActionReadRepositoryPort | None
        ) = None,
        claim_builder_output_validation_policy: (
            ClaimBuilderOutputValidationPolicy | None
        ) = None,
        draft_claim_observation_persistence: (
            PersistValidatedDraftClaimObservationsPort | None
        ) = None,
        draft_claim_observation_read_repository: (
            DraftClaimObservationReadRepositoryPort | None
        ) = None,
        work_item_split_supersede_repository: (
            WorkItemSplitSupersedeRepositoryPort | None
        ) = None,
        draft_claim_embedding_read_repository: (
            DraftClaimEmbeddingReadRepositoryPort | None
        ) = None,
        draft_claim_embedding_persistence: (
            DraftClaimEmbeddingPersistencePort | None
        ) = None,
        embedding_generation_port: EmbeddingGenerationPort | None = None,
        embedding_model_id: str | None = None,
        embedding_dimensions: int | None = None,
        draft_claim_compaction_plan_repository: (
            DraftClaimCompactionPlanRepositoryPort | None
        ) = None,
        draft_claim_compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort | None
        ) = None,
        curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort
        | None = None,
        curation_publication_repository: DraftClaimCurationPublicationRepositoryPort
        | None = None,
        draft_claim_compaction_output_validator: (
            DraftClaimCompactionOutputValidator | None
        ) = None,
        workflow_state_repository: (
            KnowledgeExtractionSagaStateRepositoryPort | None
        ) = None,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> DrainKnowledgeExtractionWorkflowCommandsResult:
        pending_commands = (
            await workflow_unit_of_work.command_log.list_pending_commands(
                workflow_run_id=command.workflow_run_id,
                limit=command.max_commands,
            )
        )
        if workflow_state_repository is not None:
            workflow_state = await workflow_state_repository.load_workflow_state(
                command.workflow_run_id,
            )
            if workflow_state is not None:
                cleanup_status = workflow_state.cleanup_status
                next_command_type = (
                    pending_commands[0].command_type if pending_commands else None
                )

                if isinstance(cleanup_status, str) and cleanup_status.strip():
                    return DrainKnowledgeExtractionWorkflowCommandsResult(
                        workflow_run_id=command.workflow_run_id,
                        inspected_count=1 if pending_commands else 0,
                        dispatched_count=0,
                        blocked_count=1,
                        last_blocked_command_type=next_command_type,
                        last_blocked_reason=WORKFLOW_CLEANUP_IN_PROGRESS,
                    )

                if workflow_state.status is KnowledgeExtractionWorkflowStatus.CANCELLED:
                    return DrainKnowledgeExtractionWorkflowCommandsResult(
                        workflow_run_id=command.workflow_run_id,
                        inspected_count=1 if pending_commands else 0,
                        dispatched_count=0,
                        blocked_count=1,
                        last_blocked_command_type=next_command_type,
                        last_blocked_reason=WORKFLOW_CANCELLED,
                    )

                if workflow_state.status is KnowledgeExtractionWorkflowStatus.PAUSED:
                    return DrainKnowledgeExtractionWorkflowCommandsResult(
                        workflow_run_id=command.workflow_run_id,
                        inspected_count=1 if pending_commands else 0,
                        dispatched_count=0,
                        blocked_count=1,
                        last_blocked_command_type=next_command_type,
                        last_blocked_reason=WORKFLOW_MANUALLY_PAUSED,
                    )

        dispatcher = DispatchKnowledgeExtractionWorkflowCommandHandler()

        inspected_count = 0
        dispatched_count = 0
        blocked_count = 0
        last_blocked_command_type: str | None = None
        last_blocked_reason: str | None = None

        for workflow_command in pending_commands:
            inspected_count += 1
            dispatch_result = await dispatcher.execute(
                DispatchKnowledgeExtractionWorkflowCommand(
                    workflow_command=workflow_command,
                ),
                source_unit_repository=source_unit_repository,
                knowledge_unit_of_work=knowledge_unit_of_work,
                workflow_unit_of_work=workflow_unit_of_work,
                prepare_llm_dispatch_batch=prepare_llm_dispatch_batch,
                execute_prepared_llm_dispatch_attempt=(
                    execute_prepared_llm_dispatch_attempt
                ),
                capacity_observation_repository=capacity_observation_repository,
                work_item_progress_read_repository=work_item_progress_read_repository,
                claim_builder_retry_action_read_repository=(
                    claim_builder_retry_action_read_repository
                ),
                claim_builder_output_validation_policy=(
                    claim_builder_output_validation_policy
                ),
                draft_claim_observation_persistence=(
                    draft_claim_observation_persistence
                ),
                draft_claim_observation_read_repository=(
                    draft_claim_observation_read_repository
                ),
                work_item_split_supersede_repository=(
                    work_item_split_supersede_repository
                ),
                draft_claim_embedding_read_repository=(
                    draft_claim_embedding_read_repository
                ),
                draft_claim_embedding_persistence=draft_claim_embedding_persistence,
                embedding_generation_port=embedding_generation_port,
                embedding_model_id=embedding_model_id,
                embedding_dimensions=embedding_dimensions,
                draft_claim_compaction_plan_repository=(
                    draft_claim_compaction_plan_repository
                ),
                draft_claim_compaction_reduction_state_repository=(
                    draft_claim_compaction_reduction_state_repository
                ),
                curation_workspace_repository=curation_workspace_repository,
                curation_publication_repository=curation_publication_repository,
                workflow_state_repository=workflow_state_repository,
                draft_claim_compaction_output_validator=(
                    draft_claim_compaction_output_validator
                ),
                frontend_event_projection_writer=frontend_event_projection_writer,
            )
            if not dispatch_result.dispatched:
                blocked_count += 1
                last_blocked_command_type = dispatch_result.command_type
                last_blocked_reason = dispatch_result.blocked_reason
                break
            dispatched_count += 1

        return DrainKnowledgeExtractionWorkflowCommandsResult(
            workflow_run_id=command.workflow_run_id,
            inspected_count=inspected_count,
            dispatched_count=dispatched_count,
            blocked_count=blocked_count,
            last_blocked_command_type=last_blocked_command_type,
            last_blocked_reason=last_blocked_reason,
        )

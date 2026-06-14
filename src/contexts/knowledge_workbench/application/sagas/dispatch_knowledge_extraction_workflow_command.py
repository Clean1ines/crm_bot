from __future__ import annotations

from dataclasses import dataclass
from src.contexts.knowledge_workbench.application.sagas.handle_cluster_draft_claims_command import (
    HandleClusterDraftClaimsCommand,
    HandleClusterDraftClaimsCommandHandler,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_generate_draft_claim_embeddings_command import (
    HandleGenerateDraftClaimEmbeddingsCommand,
    HandleGenerateDraftClaimEmbeddingsCommandHandler,
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
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    ExecutePreparedLlmDispatchAttemptPort,
    HandleExecuteClaimBuilderSectionCommand,
    HandleExecuteClaimBuilderSectionCommandHandler,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    HandlePrepareClaimBuilderDispatchBatchCommand,
    HandlePrepareClaimBuilderDispatchBatchCommandHandler,
    PrepareLlmDispatchBatchPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_reconcile_claim_builder_progress_command import (
    HandleReconcileClaimBuilderProgressCommand,
    HandleReconcileClaimBuilderProgressCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.handle_schedule_claim_builder_section_work_command import (
    HandleScheduleClaimBuilderSectionWorkCommand,
    HandleScheduleClaimBuilderSectionWorkCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.handle_split_claim_builder_source_unit_command import (
    HandleSplitClaimBuilderSourceUnitCommand,
    HandleSplitClaimBuilderSourceUnitCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_command_handler_map import (
    implemented_handler_name_for,
    is_command_implemented,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    operation_by_command_type,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)


COMMAND_HANDLER_NOT_IMPLEMENTED = "COMMAND_HANDLER_NOT_IMPLEMENTED"


@dataclass(frozen=True, slots=True)
class DispatchKnowledgeExtractionWorkflowCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class DispatchKnowledgeExtractionWorkflowCommandResult:
    workflow_run_id: str
    command_type: str
    operation_key: str
    phase: str
    handler_name: str | None
    dispatched: bool
    blocked_reason: str | None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_text(self.command_type, "command_type")
        _require_non_empty_text(self.operation_key, "operation_key")
        _require_non_empty_text(self.phase, "phase")
        if self.handler_name is not None:
            _require_non_empty_text(self.handler_name, "handler_name")
        if self.dispatched and self.blocked_reason is not None:
            raise ValueError("dispatched command cannot have blocked_reason")
        if not self.dispatched and self.blocked_reason is None:
            raise ValueError("blocked command must have blocked_reason")


class DispatchKnowledgeExtractionWorkflowCommandHandler:
    async def execute(
        self,
        command: DispatchKnowledgeExtractionWorkflowCommand,
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
    ) -> DispatchKnowledgeExtractionWorkflowCommandResult:
        workflow_command = command.workflow_command
        command_type = _canonical_command_type(workflow_command.command_type)
        operation = operation_by_command_type(command_type)
        handler_name = implemented_handler_name_for(command_type)

        if not is_command_implemented(command_type):
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=None,
                dispatched=False,
                blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
        ):
            if prepare_llm_dispatch_batch is None:
                return DispatchKnowledgeExtractionWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
                HandlePrepareClaimBuilderDispatchBatchCommand(
                    workflow_command=workflow_command,
                ),
                prepare_llm_dispatch_batch=prepare_llm_dispatch_batch,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
        ):
            if (
                execute_prepared_llm_dispatch_attempt is None
                or capacity_observation_repository is None
                or claim_builder_output_validation_policy is None
                or draft_claim_observation_persistence is None
            ):
                return DispatchKnowledgeExtractionWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleExecuteClaimBuilderSectionCommandHandler().execute(
                HandleExecuteClaimBuilderSectionCommand(
                    workflow_command=workflow_command,
                ),
                execute_prepared_llm_dispatch_attempt=(
                    execute_prepared_llm_dispatch_attempt
                ),
                capacity_observation_repository=capacity_observation_repository,
                claim_builder_output_validation_policy=(
                    claim_builder_output_validation_policy
                ),
                draft_claim_observation_persistence=(
                    draft_claim_observation_persistence
                ),
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS
        ):
            if (
                work_item_progress_read_repository is None
                or claim_builder_retry_action_read_repository is None
            ):
                return DispatchKnowledgeExtractionWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleReconcileClaimBuilderProgressCommandHandler().execute(
                HandleReconcileClaimBuilderProgressCommand(
                    workflow_command=workflow_command,
                ),
                work_item_progress_read_repository=work_item_progress_read_repository,
                claim_builder_retry_action_read_repository=(
                    claim_builder_retry_action_read_repository
                ),
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT
        ):
            if work_item_split_supersede_repository is None:
                return DispatchKnowledgeExtractionWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
                )

            await HandleSplitClaimBuilderSourceUnitCommandHandler().execute(
                HandleSplitClaimBuilderSourceUnitCommand(
                    workflow_command=workflow_command,
                ),
                source_management_repository=source_unit_repository,
                work_item_scheduling_repository=knowledge_unit_of_work,
                work_item_split_supersede_repository=(
                    work_item_split_supersede_repository
                ),
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
        ):
            await HandleScheduleClaimBuilderSectionWorkCommandHandler().execute(
                HandleScheduleClaimBuilderSectionWorkCommand(
                    workflow_command=workflow_command,
                ),
                source_unit_repository=source_unit_repository,
                knowledge_unit_of_work=knowledge_unit_of_work,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS
        ):
            if (
                draft_claim_embedding_read_repository is None
                or draft_claim_embedding_persistence is None
                or embedding_generation_port is None
                or embedding_model_id is None
                or embedding_dimensions is None
            ):
                return DispatchKnowledgeExtractionWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleGenerateDraftClaimEmbeddingsCommandHandler().execute(
                HandleGenerateDraftClaimEmbeddingsCommand(
                    workflow_command=workflow_command,
                ),
                draft_claim_embedding_read_repository=draft_claim_embedding_read_repository,
                draft_claim_embedding_persistence=draft_claim_embedding_persistence,
                embedding_generation_port=embedding_generation_port,
                embedding_model_id=embedding_model_id,
                embedding_dimensions=embedding_dimensions,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        if command_type is KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS:
            if (
                draft_claim_compaction_plan_repository is None
                or draft_claim_compaction_reduction_state_repository is None
            ):
                return DispatchKnowledgeExtractionWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleClusterDraftClaimsCommandHandler().execute(
                HandleClusterDraftClaimsCommand(workflow_command=workflow_command),
                compaction_plan_repository=draft_claim_compaction_plan_repository,
                work_item_scheduling_repository=knowledge_unit_of_work,
                workflow_unit_of_work=workflow_unit_of_work,
                compaction_reduction_state_repository=(
                    draft_claim_compaction_reduction_state_repository
                ),
            )
            return DispatchKnowledgeExtractionWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=handler_name,
                dispatched=True,
                blocked_reason=None,
            )

        raise RuntimeError(f"implemented handler is not wired: {command_type.value}")


def _canonical_command_type(
    command_type: str,
) -> KnowledgeExtractionCanonicalCommandType:
    try:
        return KnowledgeExtractionCanonicalCommandType(command_type)
    except ValueError as exc:
        raise ValueError(
            f"unknown knowledge extraction command type: {command_type}"
        ) from exc


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")

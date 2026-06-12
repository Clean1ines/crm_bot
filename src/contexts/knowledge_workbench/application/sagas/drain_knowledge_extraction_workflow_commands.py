from __future__ import annotations

from dataclasses import dataclass

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.dispatch_knowledge_extraction_workflow_command import (
    DispatchKnowledgeExtractionWorkflowCommand,
    DispatchKnowledgeExtractionWorkflowCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    ExecutePreparedLlmDispatchAttemptPort,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
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
        claim_builder_output_validation_policy: (
            ClaimBuilderOutputValidationPolicy | None
        ) = None,
    ) -> DrainKnowledgeExtractionWorkflowCommandsResult:
        pending_commands = (
            await workflow_unit_of_work.command_log.list_pending_commands(
                workflow_run_id=command.workflow_run_id,
                limit=command.max_commands,
            )
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
                claim_builder_output_validation_policy=(
                    claim_builder_output_validation_policy
                ),
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

from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    HandlePrepareClaimBuilderDispatchBatchCommand,
    HandlePrepareClaimBuilderDispatchBatchCommandHandler,
    PrepareLlmDispatchBatchPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_schedule_claim_builder_section_work_command import (
    HandleScheduleClaimBuilderSectionWorkCommand,
    HandleScheduleClaimBuilderSectionWorkCommandHandler,
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

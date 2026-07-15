from __future__ import annotations

from dataclasses import dataclass

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation_command import (
    ExecuteWorkbenchRagEvalQuestionGenerationPort,
    HandleExecuteWorkbenchRagEvalQuestionGenerationCommand,
    HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_adjudication_command import (
    ExecuteWorkbenchRagEvalAdjudicationPort,
    HandleExecuteWorkbenchRagEvalAdjudicationCommand,
    HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_prepare_workbench_rag_eval_adjudication_dispatch_batch import (
    HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommand,
    HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_prepare_workbench_rag_eval_question_generation_dispatch_batch import (
    HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand,
    HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler,
    PrepareLlmDispatchBatchPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_adjudication_progress_command import (
    HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand,
    HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_question_generation_progress_command import (
    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand,
    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler,
    QuestionGenerationPersistenceCoveragePort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_retrieval_evaluation_command import (
    HandleRunWorkbenchRagEvalRetrievalEvaluationCommand,
    HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler,
    PublishedWorkbenchSearchPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_post_promotion_verification_command import (
    HandleRunWorkbenchRagEvalPostPromotionVerificationCommand,
    HandleRunWorkbenchRagEvalPostPromotionVerificationCommandHandler,
    RunWorkbenchRagEvalPostPromotionVerificationPort,
)
from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_schedule_workbench_rag_eval_adjudication_work_command import (
    HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand,
    HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    command_type_from_value,
    operation_for_command_type,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)


RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED = "RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED"


@dataclass(frozen=True, slots=True)
class DispatchWorkbenchRagEvalWorkflowCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class DispatchWorkbenchRagEvalWorkflowCommandResult:
    workflow_run_id: str
    command_type: str
    operation_key: str
    phase: str
    handler_name: str | None
    dispatched: bool
    blocked_reason: str | None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("workflow_run_id", self.workflow_run_id),
            ("command_type", self.command_type),
            ("operation_key", self.operation_key),
            ("phase", self.phase),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.dispatched and self.blocked_reason is not None:
            raise ValueError("dispatched command cannot have blocked_reason")
        if not self.dispatched and self.blocked_reason is None:
            raise ValueError("blocked command must have blocked_reason")


class DispatchWorkbenchRagEvalWorkflowCommandHandler:
    async def execute(
        self,
        command: DispatchWorkbenchRagEvalWorkflowCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        prepare_llm_dispatch_batch: PrepareLlmDispatchBatchPort | None,
        question_generation_executor: (
            ExecuteWorkbenchRagEvalQuestionGenerationPort | None
        ) = None,
        adjudication_executor: ExecuteWorkbenchRagEvalAdjudicationPort | None = None,
        capacity_observation_repository: (
            LlmAttemptCapacityObservationRepositoryPort | None
        ) = None,
        work_item_progress_read_repository: WorkItemProgressReadRepositoryPort
        | None = None,
        question_coverage_repository: QuestionGenerationPersistenceCoveragePort
        | None = None,
        rag_eval_repository: WorkbenchRagEvalRepositoryPort | None = None,
        search_published_workbench_runtime: PublishedWorkbenchSearchPort | None = None,
        work_item_scheduling_repository: WorkItemSchedulingRepositoryPort | None = None,
        adjudication_provider_messages_builder: object | None = None,
        adjudication_model_profile: ModelProfile | None = None,
        post_promotion_verification_executor: (
            RunWorkbenchRagEvalPostPromotionVerificationPort | None
        ) = None,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> DispatchWorkbenchRagEvalWorkflowCommandResult:
        workflow_command = command.workflow_command
        command_type = command_type_from_value(workflow_command.command_type)
        operation = operation_for_command_type(command_type)

        if (
            command_type
            is WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK
        ):
            if (
                rag_eval_repository is None
                or work_item_scheduling_repository is None
                or adjudication_provider_messages_builder is None
                or adjudication_model_profile is None
            ):
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await (
                HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler().execute(
                    HandleScheduleWorkbenchRagEvalAdjudicationWorkCommand(
                        workflow_command
                    ),
                    rag_eval_repository=rag_eval_repository,
                    work_item_scheduling_repository=work_item_scheduling_repository,
                    workflow_unit_of_work=workflow_unit_of_work,
                    provider_messages_builder=adjudication_provider_messages_builder,
                    adjudication_model_profile=adjudication_model_profile,
                )
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name="HandleScheduleWorkbenchRagEvalAdjudicationWorkCommandHandler",
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH
        ):
            if prepare_llm_dispatch_batch is None:
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommandHandler().execute(
                HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommand(
                    workflow_command
                ),
                prepare_llm_dispatch_batch=prepare_llm_dispatch_batch,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name="HandlePrepareWorkbenchRagEvalAdjudicationDispatchBatchCommandHandler",
                dispatched=True,
                blocked_reason=None,
            )

        if command_type is WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION:
            if adjudication_executor is None or capacity_observation_repository is None:
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler().execute(
                HandleExecuteWorkbenchRagEvalAdjudicationCommand(workflow_command),
                adjudication_executor=adjudication_executor,
                capacity_observation_repository=capacity_observation_repository,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name="HandleExecuteWorkbenchRagEvalAdjudicationCommandHandler",
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS
        ):
            if (
                work_item_progress_read_repository is None
                or rag_eval_repository is None
            ):
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler().execute(
                HandleReconcileWorkbenchRagEvalAdjudicationProgressCommand(
                    workflow_command
                ),
                work_item_progress_read_repository=work_item_progress_read_repository,
                adjudication_coverage_repository=rag_eval_repository,
                rag_eval_repository=rag_eval_repository,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name="HandleReconcileWorkbenchRagEvalAdjudicationProgressCommandHandler",
                dispatched=True,
                blocked_reason=None,
            )

        if command_type is WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION:
            if (
                rag_eval_repository is None
                or search_published_workbench_runtime is None
            ):
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler().execute(
                HandleRunWorkbenchRagEvalRetrievalEvaluationCommand(workflow_command),
                search_published_workbench_runtime=search_published_workbench_runtime,
                rag_eval_repository=rag_eval_repository,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name="HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler",
                dispatched=True,
                blocked_reason=None,
            )

        if (
            command_type
            is WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION
        ):
            if post_promotion_verification_executor is None:
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleRunWorkbenchRagEvalPostPromotionVerificationCommandHandler().execute(
                HandleRunWorkbenchRagEvalPostPromotionVerificationCommand(
                    workflow_command
                ),
                post_promotion_verification_executor=(
                    post_promotion_verification_executor
                ),
                workflow_unit_of_work=workflow_unit_of_work,
                frontend_event_projection_writer=frontend_event_projection_writer,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=(
                    "HandleRunWorkbenchRagEvalPostPromotionVerificationCommandHandler"
                ),
                dispatched=True,
                blocked_reason=None,
            )

        if command_type is (
            WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH
        ):
            handler_name = (
                "HandlePrepareWorkbenchRagEvalQuestionGeneration"
                "DispatchBatchCommandHandler"
            )
            if prepare_llm_dispatch_batch is None:
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommandHandler().execute(
                HandlePrepareWorkbenchRagEvalQuestionGenerationDispatchBatchCommand(
                    workflow_command=workflow_command,
                ),
                prepare_llm_dispatch_batch=prepare_llm_dispatch_batch,
                workflow_unit_of_work=workflow_unit_of_work,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
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
            is WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS
        ):
            if (
                work_item_progress_read_repository is None
                or question_coverage_repository is None
                or rag_eval_repository is None
            ):
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
                )
            await HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler().execute(
                HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                    workflow_command
                ),
                work_item_progress_read_repository=work_item_progress_read_repository,
                question_coverage_repository=question_coverage_repository,
                workflow_unit_of_work=workflow_unit_of_work,
                rag_eval_repository=rag_eval_repository,
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name="HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler",
                dispatched=True,
                blocked_reason=None,
            )

        if command_type is (
            WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION
        ):
            if (
                question_generation_executor is None
                or capacity_observation_repository is None
            ):
                return DispatchWorkbenchRagEvalWorkflowCommandResult(
                    workflow_run_id=workflow_command.workflow_run_id,
                    command_type=command_type.value,
                    operation_key=operation.operation_key,
                    phase=operation.phase.value,
                    handler_name=None,
                    dispatched=False,
                    blocked_reason=(RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED),
                )

            await (
                HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler().execute(
                    HandleExecuteWorkbenchRagEvalQuestionGenerationCommand(
                        workflow_command=workflow_command,
                    ),
                    question_generation_executor=(question_generation_executor),
                    capacity_observation_repository=(capacity_observation_repository),
                    workflow_unit_of_work=workflow_unit_of_work,
                )
            )
            return DispatchWorkbenchRagEvalWorkflowCommandResult(
                workflow_run_id=workflow_command.workflow_run_id,
                command_type=command_type.value,
                operation_key=operation.operation_key,
                phase=operation.phase.value,
                handler_name=(
                    "HandleExecuteWorkbenchRagEvalQuestionGenerationCommandHandler"
                ),
                dispatched=True,
                blocked_reason=None,
            )

        return DispatchWorkbenchRagEvalWorkflowCommandResult(
            workflow_run_id=workflow_command.workflow_run_id,
            command_type=command_type.value,
            operation_key=operation.operation_key,
            phase=operation.phase.value,
            handler_name=None,
            dispatched=False,
            blocked_reason=RAG_EVAL_COMMAND_HANDLER_NOT_IMPLEMENTED,
        )

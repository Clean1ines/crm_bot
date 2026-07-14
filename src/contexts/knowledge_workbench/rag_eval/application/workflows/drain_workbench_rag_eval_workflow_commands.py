from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.workflows.dispatch_workbench_rag_eval_workflow_command import (
    DispatchWorkbenchRagEvalWorkflowCommand,
    DispatchWorkbenchRagEvalWorkflowCommandHandler,
)
from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation_command import (
    ExecuteWorkbenchRagEvalQuestionGenerationPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_adjudication_command import (
    ExecuteWorkbenchRagEvalAdjudicationPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_prepare_workbench_rag_eval_question_generation_dispatch_batch import (
    PrepareLlmDispatchBatchPort,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_question_generation_progress_command import (
    QuestionGenerationPersistenceCoveragePort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_retrieval_evaluation_command import (
    PublishedWorkbenchSearchPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_post_promotion_verification_command import (
    RunWorkbenchRagEvalPostPromotionVerificationPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)


@dataclass(frozen=True, slots=True)
class DrainWorkbenchRagEvalWorkflowCommandsCommand:
    workflow_run_id: str
    max_commands: int = 10

    def __post_init__(self) -> None:
        if (
            not isinstance(self.workflow_run_id, str)
            or not self.workflow_run_id.strip()
        ):
            raise ValueError("workflow_run_id must be non-empty")
        if isinstance(self.max_commands, bool) or not isinstance(
            self.max_commands, int
        ):
            raise TypeError("max_commands must be int")
        if self.max_commands <= 0:
            raise ValueError("max_commands must be > 0")


@dataclass(frozen=True, slots=True)
class DrainWorkbenchRagEvalWorkflowCommandsResult:
    workflow_run_id: str
    inspected_count: int
    dispatched_count: int
    blocked_count: int
    last_blocked_command_type: str | None
    last_blocked_reason: str | None


class DrainWorkbenchRagEvalWorkflowCommands:
    async def execute(
        self,
        command: DrainWorkbenchRagEvalWorkflowCommandsCommand,
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
        post_promotion_verification_executor: (
            RunWorkbenchRagEvalPostPromotionVerificationPort | None
        ) = None,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> DrainWorkbenchRagEvalWorkflowCommandsResult:
        pending_commands = (
            await workflow_unit_of_work.command_log.list_pending_commands(
                workflow_run_id=command.workflow_run_id,
                limit=command.max_commands,
            )
        )

        dispatcher = DispatchWorkbenchRagEvalWorkflowCommandHandler()
        inspected_count = 0
        dispatched_count = 0
        blocked_count = 0
        last_blocked_command_type: str | None = None
        last_blocked_reason: str | None = None

        for workflow_command in pending_commands:
            inspected_count += 1
            result = await dispatcher.execute(
                DispatchWorkbenchRagEvalWorkflowCommand(
                    workflow_command=workflow_command,
                ),
                workflow_unit_of_work=workflow_unit_of_work,
                prepare_llm_dispatch_batch=prepare_llm_dispatch_batch,
                question_generation_executor=(question_generation_executor),
                adjudication_executor=adjudication_executor,
                capacity_observation_repository=(capacity_observation_repository),
                work_item_progress_read_repository=work_item_progress_read_repository,
                question_coverage_repository=question_coverage_repository,
                rag_eval_repository=rag_eval_repository,
                search_published_workbench_runtime=search_published_workbench_runtime,
                work_item_scheduling_repository=work_item_scheduling_repository,
                adjudication_provider_messages_builder=(
                    adjudication_provider_messages_builder
                ),
                post_promotion_verification_executor=(
                    post_promotion_verification_executor
                ),
                frontend_event_projection_writer=frontend_event_projection_writer,
            )
            if not result.dispatched:
                blocked_count = 1
                last_blocked_command_type = result.command_type
                last_blocked_reason = result.blocked_reason
                break
            dispatched_count += 1

        return DrainWorkbenchRagEvalWorkflowCommandsResult(
            workflow_run_id=command.workflow_run_id,
            inspected_count=inspected_count,
            dispatched_count=dispatched_count,
            blocked_count=blocked_count,
            last_blocked_command_type=last_blocked_command_type,
            last_blocked_reason=last_blocked_reason,
        )

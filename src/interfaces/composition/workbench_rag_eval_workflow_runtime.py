from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.capacity_runtime.infrastructure.postgres.postgres_llm_attempt_capacity_observation_repository import (
    PostgresLlmAttemptCapacityObservationRepository,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcome,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_read_repository import (
    PostgresReadWorkItemAttemptDispatchRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_outcome_repository import (
    PostgresWorkItemAttemptOutcomeRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_progress_read_repository import (
    PostgresWorkItemProgressReadRepository,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.drain_workbench_rag_eval_workflow_commands import (
    DrainWorkbenchRagEvalWorkflowCommands,
    DrainWorkbenchRagEvalWorkflowCommandsCommand,
    DrainWorkbenchRagEvalWorkflowCommandsResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_execute_workbench_rag_eval_question_generation import (
    ExecuteWorkbenchRagEvalQuestionGeneration,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    make_adjudication_dispatch_preparation_builder,
    make_question_generation_dispatch_preparation_builder,
    workbench_rag_eval_route_catalog,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.postgres.postgres_llm_route_capacity_reservation_repository import (
    PostgresLlmRouteCapacityReservationRepository,
    actual_tokens_from_capacity_observation,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.llm_dispatch_executor import (
    make_llm_dispatch_executor_from_settings,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    AsyncPool as PrepareAsyncPool,
    DispatchPreparationBuilderRegistry,
    PrepareLlmDispatchBatch,
)


class RuntimePool(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class DueWorkbenchRagEvalWorkflow:
    project_id: str
    workflow_run_id: str


@dataclass(frozen=True, slots=True)
class TransactionalExecutePreparedLlmDispatchAttempt:
    pool: RuntimePool
    llm_executor: LlmDispatchExecutorPort

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        connection = await self.pool.acquire()
        try:
            asyncpg_connection = cast(asyncpg.Connection, connection)
            async with asyncpg_connection.transaction():
                outcome_repository = PostgresWorkItemAttemptOutcomeRepository(
                    asyncpg_connection
                )
                result = await ExecutePreparedLlmDispatchAttempt(
                    dispatch_repository=PostgresReadWorkItemAttemptDispatchRepository(
                        asyncpg_connection
                    ),
                    llm_executor=self.llm_executor,
                    outcome_recorder=RecordWorkItemAttemptOutcome(
                        repository=outcome_repository
                    ),
                    recorded_outcome_reader=outcome_repository,
                ).execute(command)
                actual_tokens = actual_tokens_from_capacity_observation(
                    result.llm_result.capacity_observation
                )
                await PostgresLlmRouteCapacityReservationRepository(
                    asyncpg_connection
                ).finalize(
                    attempt_id=result.dispatch.attempt_id,
                    final_status="committed"
                    if actual_tokens is not None
                    else "released",
                    actual_tokens=actual_tokens,
                    finalized_at=result.llm_result.finished_at,
                )
                return result
        finally:
            await self.pool.release(connection)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalWorkflowRuntimeComposition:
    pool: RuntimePool
    llm_executor: LlmDispatchExecutorPort
    prepare_llm_dispatch_batch: PrepareLlmDispatchBatch
    execute_prepared_llm_dispatch_attempt: (
        TransactionalExecutePreparedLlmDispatchAttempt
    )

    async def execute(
        self,
        *,
        workflow_run_id: str,
        max_commands: int,
    ) -> DrainWorkbenchRagEvalWorkflowCommandsResult:
        connection = await self.pool.acquire()
        unit_of_work: PostgresWorkflowRuntimeUnitOfWork | None = None
        try:
            asyncpg_connection = cast(asyncpg.Connection, connection)
            unit_of_work = PostgresWorkflowRuntimeUnitOfWork(asyncpg_connection)
            await unit_of_work.start()
            repository = PostgresWorkbenchRagEvalRepository(asyncpg_connection)
            result = await DrainWorkbenchRagEvalWorkflowCommands().execute(
                DrainWorkbenchRagEvalWorkflowCommandsCommand(
                    workflow_run_id=workflow_run_id,
                    max_commands=max_commands,
                ),
                workflow_unit_of_work=unit_of_work,
                prepare_llm_dispatch_batch=self.prepare_llm_dispatch_batch,
                question_generation_executor=ExecuteWorkbenchRagEvalQuestionGeneration(
                    execute_prepared_llm_dispatch_attempt=(
                        self.execute_prepared_llm_dispatch_attempt
                    ),
                    rag_eval_repository=repository,
                    question_generator=WorkbenchRagEvalQuestionGenerator.from_prompt_file(),
                ),
                capacity_observation_repository=(
                    PostgresLlmAttemptCapacityObservationRepository(asyncpg_connection)
                ),
                work_item_progress_read_repository=(
                    PostgresWorkItemProgressReadRepository(asyncpg_connection)
                ),
                question_coverage_repository=repository,
            )
            await unit_of_work.commit()
            return result
        except Exception:
            if unit_of_work is not None:
                await unit_of_work.rollback()
            raise
        finally:
            await self.pool.release(connection)

    async def run_due_once(
        self,
        *,
        workflow_batch_size: int,
        max_commands: int,
    ) -> tuple[DrainWorkbenchRagEvalWorkflowCommandsResult, ...]:
        due = await self._list_due_workflows(limit=workflow_batch_size)
        results = []
        for workflow in due:
            results.append(
                await self.execute(
                    workflow_run_id=workflow.workflow_run_id,
                    max_commands=max_commands,
                )
            )
        return tuple(results)

    async def _list_due_workflows(
        self, *, limit: int
    ) -> tuple[DueWorkbenchRagEvalWorkflow, ...]:
        connection = await self.pool.acquire()
        try:
            rows = await cast(asyncpg.Connection, connection).fetch(
                """
                SELECT run.project_id::text AS project_id, command.workflow_run_id
                FROM workflow_runtime_command_log AS command
                JOIN knowledge_workbench_rag_eval_runs AS run
                  ON run.run_id = command.workflow_run_id
                WHERE command.status = 'PENDING'
                  AND command.run_after <= NOW()
                  AND run.status NOT IN ('completed', 'blocked', 'failed')
                GROUP BY run.project_id, command.workflow_run_id
                ORDER BY MIN(command.run_after), command.workflow_run_id
                LIMIT $1
                """,
                limit,
            )
            return tuple(_due_workflow_from_row(row) for row in rows)
        finally:
            await self.pool.release(connection)


def make_workbench_rag_eval_workflow_runtime(
    *,
    pool: object,
    llm_runtime_settings: LlmRuntimeSettings | None = None,
    llm_executor: LlmDispatchExecutorPort | None = None,
) -> WorkbenchRagEvalWorkflowRuntimeComposition:
    settings = llm_runtime_settings or LlmRuntimeSettings.from_env_mapping(os.environ)
    resolved_executor = llm_executor or make_llm_dispatch_executor_from_settings(
        settings
    )
    account_refs = tuple(
        account.account_seed.account_ref
        for account in settings.to_groq_env_config().accounts
    )
    runtime_pool = cast(RuntimePool, pool)
    prepare = PrepareLlmDispatchBatch(
        pool=cast(PrepareAsyncPool, runtime_pool),
        capacity_policy=CapacityAdmissionPolicy(),
        active_model_capacity_selector=SelectActiveLlmModelCapacity(
            projector=ProjectLlmCapacityToCapacityRuntime()
        ),
        route_catalog=workbench_rag_eval_route_catalog(),
        provider_account_refs=account_refs,
        model_profiles=build_groq_free_plan_model_profiles(),
        dispatch_preparation_builder_registry=DispatchPreparationBuilderRegistry(
            builders_by_work_kind={
                WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND: (
                    make_question_generation_dispatch_preparation_builder()
                ),
                WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND: (
                    make_adjudication_dispatch_preparation_builder()
                ),
            }
        ),
    )
    transactional_execute = TransactionalExecutePreparedLlmDispatchAttempt(
        pool=runtime_pool,
        llm_executor=resolved_executor,
    )
    return WorkbenchRagEvalWorkflowRuntimeComposition(
        pool=runtime_pool,
        llm_executor=resolved_executor,
        prepare_llm_dispatch_batch=prepare,
        execute_prepared_llm_dispatch_attempt=transactional_execute,
    )


def _due_workflow_from_row(row: Mapping[str, object]) -> DueWorkbenchRagEvalWorkflow:
    project_id = row.get("project_id")
    workflow_run_id = row.get("workflow_run_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id must be non-empty")
    if not isinstance(workflow_run_id, str) or not workflow_run_id.strip():
        raise ValueError("workflow_run_id must be non-empty")
    return DueWorkbenchRagEvalWorkflow(project_id, workflow_run_id)

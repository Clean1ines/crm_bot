from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.capacity_runtime.infrastructure.postgres.postgres_llm_attempt_capacity_observation_repository import (
    PostgresLlmAttemptCapacityObservationRepository,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
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
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_split_supersede_repository import (
    PostgresWorkItemSplitSupersedeRepository,
)
from src.contexts.knowledge_workbench.application.sagas.drain_knowledge_extraction_workflow_commands import (
    DrainKnowledgeExtractionWorkflowCommands,
    DrainKnowledgeExtractionWorkflowCommandsCommand,
    DrainKnowledgeExtractionWorkflowCommandsResult,
)
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    ExecutePreparedLlmDispatchAttemptPort,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    PrepareLlmDispatchBatchPort,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsPort,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_builder_retry_action_read_repository import (
    PostgresClaimBuilderRetryActionReadRepository,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_validated_draft_claim_observation_persistence import (
    PostgresValidatedDraftClaimObservationPersistence,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    PostgresSourceManagementRepository,
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
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttempt,
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    AsyncPool,
    PrepareLlmDispatchBatch,
)


class KnowledgeExtractionWorkflowResumeNotFoundError(LookupError):
    pass


class _AsyncResumePoolLike(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionWorkflowResumeCommand:
    project_id: str
    document_id: str
    max_drain_commands: int = 10

    def __post_init__(self) -> None:
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(self.document_id, field_name="document_id")
        if not isinstance(self.max_drain_commands, int):
            raise TypeError("max_drain_commands must be int")
        if self.max_drain_commands <= 0:
            raise ValueError("max_drain_commands must be > 0")


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionWorkflowResumeResult:
    workflow_run_id: str
    source_document_ref: str
    drained_inspected_count: int
    drained_dispatched_count: int
    blocked_command_type: str | None
    blocked_reason: str | None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        for field_name, value in (
            ("drained_inspected_count", self.drained_inspected_count),
            ("drained_dispatched_count", self.drained_dispatched_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if (
            self.blocked_command_type is not None
            and not self.blocked_command_type.strip()
        ):
            raise ValueError("blocked_command_type must be non-empty when set")
        if self.blocked_reason is not None and not self.blocked_reason.strip():
            raise ValueError("blocked_reason must be non-empty when set")


@dataclass(frozen=True, slots=True)
class _ResolvedWorkflow:
    workflow_run_id: str
    source_document_ref: str


class RunKnowledgeExtractionWorkflowResume:
    def __init__(
        self,
        *,
        pool: object,
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
        draft_claim_observation_persistence: (
            PersistValidatedDraftClaimObservationsPort | None
        ) = None,
    ) -> None:
        self._pool = cast(_AsyncResumePoolLike, pool)
        self._prepare_llm_dispatch_batch = prepare_llm_dispatch_batch
        self._execute_prepared_llm_dispatch_attempt = (
            execute_prepared_llm_dispatch_attempt
        )
        self._capacity_observation_repository = capacity_observation_repository
        self._work_item_progress_read_repository = work_item_progress_read_repository
        self._claim_builder_output_validation_policy = (
            claim_builder_output_validation_policy
            or ClaimBuilderOutputValidationPolicy()
        )
        self._draft_claim_observation_persistence = draft_claim_observation_persistence

    async def execute(
        self,
        command: RunKnowledgeExtractionWorkflowResumeCommand,
    ) -> RunKnowledgeExtractionWorkflowResumeResult:
        workflow = await self._resolve_workflow(command)
        if workflow is None:
            raise KnowledgeExtractionWorkflowResumeNotFoundError(
                "knowledge extraction workflow not found"
            )

        drain_result = await self._drain_until_blocked_or_idle(
            workflow_run_id=workflow.workflow_run_id,
            max_drain_commands=command.max_drain_commands,
        )

        return RunKnowledgeExtractionWorkflowResumeResult(
            workflow_run_id=workflow.workflow_run_id,
            source_document_ref=workflow.source_document_ref,
            drained_inspected_count=drain_result.drained_inspected_count,
            drained_dispatched_count=drain_result.drained_dispatched_count,
            blocked_command_type=drain_result.blocked_command_type,
            blocked_reason=drain_result.blocked_reason,
        )

    async def _resolve_workflow(
        self,
        command: RunKnowledgeExtractionWorkflowResumeCommand,
    ) -> _ResolvedWorkflow | None:
        connection = await self._pool.acquire()
        try:
            row = await cast(asyncpg.Connection, connection).fetchrow(
                """
                SELECT workflow_run_id, source_document_ref
                FROM knowledge_extraction_workflow_runs
                WHERE project_id = $1
                  AND (
                    workflow_run_id = $2
                    OR source_document_ref = $2
                  )
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                command.project_id,
                command.document_id,
            )
        finally:
            await self._pool.release(connection)

        if row is None:
            return None

        row_mapping = cast(Mapping[str, object], row)
        workflow_run_id = _text_from_row(row_mapping, "workflow_run_id")
        source_document_ref = _text_from_row(row_mapping, "source_document_ref")
        return _ResolvedWorkflow(
            workflow_run_id=workflow_run_id,
            source_document_ref=source_document_ref,
        )

    async def _drain_until_blocked_or_idle(
        self,
        *,
        workflow_run_id: str,
        max_drain_commands: int,
    ) -> RunKnowledgeExtractionWorkflowResumeResult:
        remaining_commands = max_drain_commands
        inspected_count = 0
        dispatched_count = 0
        blocked_command_type: str | None = None
        blocked_reason: str | None = None

        while remaining_commands > 0:
            drain_result = await self._run_one_drain_transaction(
                workflow_run_id=workflow_run_id,
                max_commands=remaining_commands,
            )
            inspected_count += drain_result.inspected_count
            dispatched_count += drain_result.dispatched_count

            if drain_result.blocked_count > 0:
                blocked_command_type = drain_result.last_blocked_command_type
                blocked_reason = drain_result.last_blocked_reason
                break

            if drain_result.inspected_count == 0 or drain_result.dispatched_count == 0:
                break

            remaining_commands -= drain_result.inspected_count

        return RunKnowledgeExtractionWorkflowResumeResult(
            workflow_run_id=workflow_run_id,
            source_document_ref=workflow_run_id,
            drained_inspected_count=inspected_count,
            drained_dispatched_count=dispatched_count,
            blocked_command_type=blocked_command_type,
            blocked_reason=blocked_reason,
        )

    async def _run_one_drain_transaction(
        self,
        *,
        workflow_run_id: str,
        max_commands: int,
    ) -> DrainKnowledgeExtractionWorkflowCommandsResult:
        connection = await self._pool.acquire()
        workflow_unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
            cast(asyncpg.Connection, connection),
        )
        await workflow_unit_of_work.start()

        try:
            result = await DrainKnowledgeExtractionWorkflowCommands().execute(
                DrainKnowledgeExtractionWorkflowCommandsCommand(
                    workflow_run_id=workflow_run_id,
                    max_commands=max_commands,
                ),
                source_unit_repository=PostgresSourceManagementRepository(
                    cast(asyncpg.Connection, connection),
                ),
                knowledge_unit_of_work=PostgresWorkItemSchedulingRepository(
                    cast(asyncpg.Connection, connection),
                ),
                work_item_split_supersede_repository=(
                    PostgresWorkItemSplitSupersedeRepository(
                        cast(asyncpg.Connection, connection),
                    )
                ),
                workflow_unit_of_work=workflow_unit_of_work,
                prepare_llm_dispatch_batch=self._prepare_llm_dispatch_batch,
                execute_prepared_llm_dispatch_attempt=(
                    self._execute_prepared_llm_dispatch_attempt
                ),
                capacity_observation_repository=(
                    self._capacity_observation_repository
                    or PostgresLlmAttemptCapacityObservationRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                work_item_progress_read_repository=(
                    self._work_item_progress_read_repository
                    or PostgresWorkItemProgressReadRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                claim_builder_retry_action_read_repository=(
                    PostgresClaimBuilderRetryActionReadRepository(
                        cast(asyncpg.Connection, connection)
                    )
                ),
                claim_builder_output_validation_policy=(
                    self._claim_builder_output_validation_policy
                ),
                draft_claim_observation_persistence=(
                    self._draft_claim_observation_persistence
                    or PostgresValidatedDraftClaimObservationPersistence(
                        cast(asyncpg.Connection, connection)
                    )
                ),
            )
            await workflow_unit_of_work.commit()
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self._pool.release(connection)


@dataclass(frozen=True, slots=True)
class _TransactionalExecutePreparedLlmDispatchAttempt:
    pool: AsyncPool
    llm_executor: LlmDispatchExecutorPort

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> ExecutePreparedLlmDispatchAttemptResult:
        connection = await self.pool.acquire()
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                return await ExecutePreparedLlmDispatchAttempt(
                    dispatch_repository=PostgresReadWorkItemAttemptDispatchRepository(
                        asyncpg_connection,
                    ),
                    llm_executor=self.llm_executor,
                    outcome_recorder=RecordWorkItemAttemptOutcome(
                        repository=PostgresWorkItemAttemptOutcomeRepository(
                            asyncpg_connection,
                        ),
                    ),
                ).execute(command)
        finally:
            await self.pool.release(connection)


def make_knowledge_extraction_workflow_resume(
    *,
    pool: AsyncPool,
    llm_executor: LlmDispatchExecutorPort | None = None,
) -> RunKnowledgeExtractionWorkflowResume:
    if llm_executor is None:
        return RunKnowledgeExtractionWorkflowResume(
            pool=pool,
            claim_builder_output_validation_policy=ClaimBuilderOutputValidationPolicy(),
        )

    route_catalog = default_groq_llm_model_route_catalog()

    return RunKnowledgeExtractionWorkflowResume(
        pool=pool,
        prepare_llm_dispatch_batch=PrepareLlmDispatchBatch(
            pool=pool,
            capacity_policy=CapacityAdmissionPolicy(),
            active_model_capacity_selector=SelectActiveLlmModelCapacity(
                projector=ProjectLlmCapacityToCapacityRuntime(),
            ),
            route_catalog=route_catalog,
        ),
        execute_prepared_llm_dispatch_attempt=(
            _TransactionalExecutePreparedLlmDispatchAttempt(
                pool=pool,
                llm_executor=llm_executor,
            )
        ),
        claim_builder_output_validation_policy=ClaimBuilderOutputValidationPolicy(),
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _text_from_row(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty str")
    return value

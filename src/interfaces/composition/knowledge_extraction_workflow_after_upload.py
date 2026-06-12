from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservationRepositoryPort,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressReadRepositoryPort,
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
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_builder_retry_action_read_repository import (
    PostgresClaimBuilderRetryActionReadRepository,
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
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    PostgresSourceManagementRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)


class SourceIngestionFirstPhaseRunnerPort(Protocol):
    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult: ...


class _AsyncDrainPoolLike(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionWorkflowAfterUploadCommand:
    source_ingestion_command: RunSourceIngestionFirstPhaseCommand
    max_drain_commands: int = 10

    def __post_init__(self) -> None:
        if not isinstance(
            self.source_ingestion_command,
            RunSourceIngestionFirstPhaseCommand,
        ):
            raise TypeError(
                "source_ingestion_command must be RunSourceIngestionFirstPhaseCommand"
            )
        if not isinstance(self.max_drain_commands, int):
            raise TypeError("max_drain_commands must be int")
        if self.max_drain_commands <= 0:
            raise ValueError("max_drain_commands must be > 0")


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionWorkflowAfterUploadResult:
    workflow_run_id: str
    source_ingestion_completed: bool
    drained_inspected_count: int
    drained_dispatched_count: int
    blocked_command_type: str | None
    blocked_reason: str | None
    source_document_ref: str | None = None
    source_unit_count: int = 0
    source_ingestion_admission_status: SourceIngestionAdmissionStatus | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_run_id, str):
            raise TypeError("workflow_run_id must be str")
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
        if (
            self.source_document_ref is not None
            and not self.source_document_ref.strip()
        ):
            raise ValueError("source_document_ref must be non-empty when set")
        if not isinstance(self.source_unit_count, int):
            raise TypeError("source_unit_count must be int")
        if self.source_unit_count < 0:
            raise ValueError("source_unit_count must be >= 0")
        if self.source_ingestion_admission_status is not None and not isinstance(
            self.source_ingestion_admission_status,
            SourceIngestionAdmissionStatus,
        ):
            raise TypeError(
                "source_ingestion_admission_status must be SourceIngestionAdmissionStatus"
            )
        if (
            self.source_ingestion_completed is False
            and self.source_ingestion_admission_status is None
        ):
            raise ValueError(
                "rejected source ingestion requires source_ingestion_admission_status"
            )


class RunKnowledgeExtractionWorkflowAfterUpload:
    def __init__(
        self,
        *,
        source_ingestion_runner: SourceIngestionFirstPhaseRunnerPort,
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
    ) -> None:
        self._source_ingestion_runner = source_ingestion_runner
        self._pool = cast(_AsyncDrainPoolLike, pool)
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

    async def execute(
        self,
        command: RunKnowledgeExtractionWorkflowAfterUploadCommand,
    ) -> RunKnowledgeExtractionWorkflowAfterUploadResult:
        source_result = await self._source_ingestion_runner.execute(
            command.source_ingestion_command,
        )
        if source_result.status is not RunSourceIngestionFirstPhaseStatus.COMPLETED:
            return RunKnowledgeExtractionWorkflowAfterUploadResult(
                workflow_run_id=source_result.workflow_run_id or "",
                source_ingestion_completed=False,
                drained_inspected_count=0,
                drained_dispatched_count=0,
                blocked_command_type=None,
                blocked_reason=None,
                source_document_ref=source_result.source_document_ref,
                source_unit_count=source_result.source_unit_count,
                source_ingestion_admission_status=source_result.admission_status,
            )

        workflow_run_id = source_result.workflow_run_id
        if workflow_run_id is None or not workflow_run_id.strip():
            raise ValueError("completed source ingestion must return workflow_run_id")

        drain_result = await self._drain_until_blocked_or_idle(
            workflow_run_id=workflow_run_id,
            max_drain_commands=command.max_drain_commands,
            source_document_ref=source_result.source_document_ref,
            source_unit_count=source_result.source_unit_count,
            source_ingestion_admission_status=source_result.admission_status,
        )
        return RunKnowledgeExtractionWorkflowAfterUploadResult(
            workflow_run_id=workflow_run_id,
            source_ingestion_completed=True,
            drained_inspected_count=drain_result.drained_inspected_count,
            drained_dispatched_count=drain_result.drained_dispatched_count,
            blocked_command_type=drain_result.blocked_command_type,
            blocked_reason=drain_result.blocked_reason,
            source_document_ref=source_result.source_document_ref,
            source_unit_count=source_result.source_unit_count,
            source_ingestion_admission_status=source_result.admission_status,
        )

    async def _drain_until_blocked_or_idle(
        self,
        *,
        workflow_run_id: str,
        max_drain_commands: int,
        source_document_ref: str | None,
        source_unit_count: int,
        source_ingestion_admission_status: SourceIngestionAdmissionStatus | None,
    ) -> RunKnowledgeExtractionWorkflowAfterUploadResult:
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

        return RunKnowledgeExtractionWorkflowAfterUploadResult(
            workflow_run_id=workflow_run_id,
            source_ingestion_completed=True,
            drained_inspected_count=inspected_count,
            drained_dispatched_count=dispatched_count,
            blocked_command_type=blocked_command_type,
            blocked_reason=blocked_reason,
            source_document_ref=source_document_ref,
            source_unit_count=source_unit_count,
            source_ingestion_admission_status=source_ingestion_admission_status,
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
                capacity_observation_repository=(self._capacity_observation_repository),
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
            )
            await workflow_unit_of_work.commit()
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self._pool.release(connection)

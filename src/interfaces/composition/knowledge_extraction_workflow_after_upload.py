from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import asyncpg

from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.knowledge_workbench.application.sagas.drain_knowledge_extraction_workflow_commands import (
    DrainKnowledgeExtractionWorkflowCommands,
    DrainKnowledgeExtractionWorkflowCommandsCommand,
    DrainKnowledgeExtractionWorkflowCommandsResult,
)
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
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


class RunKnowledgeExtractionWorkflowAfterUpload:
    def __init__(
        self,
        *,
        source_ingestion_runner: SourceIngestionFirstPhaseRunnerPort,
        pool: object,
    ) -> None:
        self._source_ingestion_runner = source_ingestion_runner
        self._pool = cast(_AsyncDrainPoolLike, pool)

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
            )

        workflow_run_id = source_result.workflow_run_id
        if workflow_run_id is None or not workflow_run_id.strip():
            raise ValueError("completed source ingestion must return workflow_run_id")

        drain_result = await self._drain_until_blocked_or_idle(
            workflow_run_id=workflow_run_id,
            max_drain_commands=command.max_drain_commands,
            source_document_ref=source_result.source_document_ref,
            source_unit_count=source_result.source_unit_count,
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
        )

    async def _drain_until_blocked_or_idle(
        self,
        *,
        workflow_run_id: str,
        max_drain_commands: int,
        source_document_ref: str | None,
        source_unit_count: int,
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
                workflow_unit_of_work=workflow_unit_of_work,
            )
            await workflow_unit_of_work.commit()
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self._pool.release(connection)

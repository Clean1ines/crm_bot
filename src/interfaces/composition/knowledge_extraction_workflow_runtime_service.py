from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, cast

import asyncpg
import structlog

from src.contexts.execution_runtime.infrastructure.postgres.postgres_expired_lease_recovery_repository import (
    PostgresExpiredLeaseRecoveryRepository,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_due_knowledge_extraction_workflow_reader import (
    PostgresDueKnowledgeExtractionWorkflowReader,
)
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    AsyncPool,
    RunKnowledgeExtractionWorkflowResumeCommand,
    make_knowledge_extraction_workflow_resume,
)
from src.interfaces.composition.knowledge_extraction_workflow_runtime_pump import (
    DueKnowledgeExtractionWorkflow,
    KnowledgeExtractionWorkflowRuntimePump,
)


LOGGER = structlog.get_logger(__name__)


class AsyncPoolLike(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class _WorkflowRunner:
    pool: AsyncPoolLike
    llm_executor: LlmDispatchExecutorPort
    max_drain_commands: int

    async def run(
        self,
        *,
        project_id: str,
        workflow_run_id: str,
    ) -> None:
        await make_knowledge_extraction_workflow_resume(
            pool=cast(AsyncPool, self.pool),
            llm_executor=self.llm_executor,
        ).execute(
            RunKnowledgeExtractionWorkflowResumeCommand(
                project_id=project_id,
                document_id=workflow_run_id,
                max_drain_commands=self.max_drain_commands,
            )
        )


async def run_knowledge_extraction_workflow_runtime_loop(
    *,
    pool: AsyncPoolLike,
    llm_executor: LlmDispatchExecutorPort,
    shutdown_event: asyncio.Event,
    poll_interval_seconds: float,
    workflow_batch_size: int,
    max_drain_commands: int,
    stale_lease_batch_size: int,
) -> None:
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be > 0")

    workflow_runner = _WorkflowRunner(
        pool=pool,
        llm_executor=llm_executor,
        max_drain_commands=max_drain_commands,
    )
    LOGGER.info("knowledge_extraction_workflow_runtime_started")

    while not shutdown_event.is_set():
        connection = await pool.acquire()
        try:
            asyncpg_connection = cast(asyncpg.Connection, connection)
            async with asyncpg_connection.transaction():
                recovery = await PostgresExpiredLeaseRecoveryRepository(
                    asyncpg_connection
                ).reclaim_expired(
                    now=datetime.now(timezone.utc),
                    limit=stale_lease_batch_size,
                )
                due_reader = PostgresDueKnowledgeExtractionWorkflowReader(
                    asyncpg_connection
                )
                due_workflows = await due_reader.list_due_workflows(
                    limit=workflow_batch_size
                )
        except Exception:
            LOGGER.exception("knowledge_extraction_workflow_runtime_maintenance_failed")
            due_workflows = ()
            recovery = None
        finally:
            await pool.release(connection)

        if recovery is not None and recovery.reclaimed_count:
            LOGGER.warning(
                "knowledge_extraction_expired_leases_reclaimed",
                reclaimed_count=recovery.reclaimed_count,
                work_item_ids=recovery.reclaimed_work_item_ids,
            )

        if due_workflows:
            await KnowledgeExtractionWorkflowRuntimePump(
                due_workflow_reader=_StaticDueWorkflowReader(due_workflows),
                workflow_runner=workflow_runner,
            ).run_once(limit=len(due_workflows))

        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=poll_interval_seconds,
            )
        except TimeoutError:
            continue

    LOGGER.info("knowledge_extraction_workflow_runtime_stopped")


@dataclass(frozen=True, slots=True)
class _StaticDueWorkflowReader:
    due_workflows: tuple[DueKnowledgeExtractionWorkflow, ...]

    async def list_due_workflows(
        self,
        *,
        limit: int,
    ) -> tuple[DueKnowledgeExtractionWorkflow, ...]:
        return self.due_workflows[:limit]

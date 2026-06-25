from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import asyncpg

from src.contexts.knowledge_workbench.application.sagas.pause_knowledge_extraction_workflow import (
    PauseKnowledgeExtractionWorkflow,
    PauseKnowledgeExtractionWorkflowCommand,
    PauseKnowledgeExtractionWorkflowResult,
)
from src.contexts.knowledge_workbench.application.sagas.resume_knowledge_extraction_workflow import (
    ResumeKnowledgeExtractionWorkflow,
    ResumeKnowledgeExtractionWorkflowCommand,
    ResumeKnowledgeExtractionWorkflowResult,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    PostgresKnowledgeExtractionSagaStateRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)
from src.contexts.knowledge_workbench.observability.application.projectors.knowledge_extraction_frontend_workflow_event_projector import (
    KnowledgeExtractionFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.infrastructure.postgres.postgres_frontend_workflow_event_repository import (
    PostgresFrontendWorkflowEventRepository,
)
from src.interfaces.realtime.collecting_frontend_workflow_event_repository import (
    CollectingFrontendWorkflowEventRepository,
)
from src.interfaces.realtime.redis_frontend_workflow_event_bus import (
    publish_frontend_workflow_events,
)


class AsyncManualWorkflowPool(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class RunPauseKnowledgeExtractionWorkflow:
    pool: AsyncManualWorkflowPool

    async def execute(
        self,
        command: PauseKnowledgeExtractionWorkflowCommand,
    ) -> PauseKnowledgeExtractionWorkflowResult:
        connection = await self.pool.acquire()
        workflow_unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
            cast(asyncpg.Connection, connection),
        )
        await workflow_unit_of_work.start()

        frontend_event_repository = CollectingFrontendWorkflowEventRepository(
            inner=PostgresFrontendWorkflowEventRepository(
                cast(asyncpg.Connection, connection),
            ),
        )
        frontend_event_projection_writer = ProjectFrontendWorkflowEvent(
            projector=KnowledgeExtractionFrontendWorkflowEventProjector(),
            repository=frontend_event_repository,
        )

        try:
            result = await PauseKnowledgeExtractionWorkflow(
                state_repository=PostgresKnowledgeExtractionSagaStateRepository(
                    cast(asyncpg.Connection, connection),
                ),
                workflow_unit_of_work=workflow_unit_of_work,
            ).execute(
                command,
                frontend_event_projection_writer=frontend_event_projection_writer,
            )
            await workflow_unit_of_work.commit()
            await publish_frontend_workflow_events(
                frontend_event_repository.persisted_events()
            )
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self.pool.release(connection)


@dataclass(frozen=True, slots=True)
class RunResumeKnowledgeExtractionWorkflowTransition:
    pool: AsyncManualWorkflowPool

    async def execute(
        self,
        command: ResumeKnowledgeExtractionWorkflowCommand,
    ) -> ResumeKnowledgeExtractionWorkflowResult:
        connection = await self.pool.acquire()
        workflow_unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
            cast(asyncpg.Connection, connection),
        )
        await workflow_unit_of_work.start()

        frontend_event_repository = CollectingFrontendWorkflowEventRepository(
            inner=PostgresFrontendWorkflowEventRepository(
                cast(asyncpg.Connection, connection),
            ),
        )
        frontend_event_projection_writer = ProjectFrontendWorkflowEvent(
            projector=KnowledgeExtractionFrontendWorkflowEventProjector(),
            repository=frontend_event_repository,
        )

        try:
            result = await ResumeKnowledgeExtractionWorkflow(
                state_repository=PostgresKnowledgeExtractionSagaStateRepository(
                    cast(asyncpg.Connection, connection),
                ),
                workflow_unit_of_work=workflow_unit_of_work,
            ).execute(
                command,
                frontend_event_projection_writer=frontend_event_projection_writer,
            )
            await workflow_unit_of_work.commit()
            await publish_frontend_workflow_events(
                frontend_event_repository.persisted_events()
            )
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self.pool.release(connection)


def make_pause_knowledge_extraction_workflow(
    *,
    pool: AsyncManualWorkflowPool,
) -> RunPauseKnowledgeExtractionWorkflow:
    return RunPauseKnowledgeExtractionWorkflow(pool=pool)


def make_resume_knowledge_extraction_workflow_transition(
    *,
    pool: AsyncManualWorkflowPool,
) -> RunResumeKnowledgeExtractionWorkflowTransition:
    return RunResumeKnowledgeExtractionWorkflowTransition(pool=pool)

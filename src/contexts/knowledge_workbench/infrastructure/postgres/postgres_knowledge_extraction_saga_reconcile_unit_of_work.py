from __future__ import annotations

import asyncpg
from typing import cast

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_reconcile_unit_of_work import (
    KnowledgeExtractionSagaReconcileUnitOfWorkPort,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    PostgresKnowledgeExtractionSagaStateRepository,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    PostgresSourceManagementRepository,
)


class PostgresKnowledgeExtractionSagaReconcileUnitOfWork(
    KnowledgeExtractionSagaReconcileUnitOfWorkPort,
):
    """Postgres transaction boundary for one KnowledgeExtractionSaga.reconcile call."""

    def __init__(
        self,
        connection: asyncpg.Connection,
        *,
        command_emitter: KnowledgeExtractionCommandEmitterPort,
    ) -> None:
        self._connection = connection
        self._transaction = connection.transaction()
        self._command_emitter = command_emitter
        self._started = False
        self._closed = False
        self._saga_repository: PostgresKnowledgeExtractionSagaStateRepository | None = (
            None
        )
        self._source_repository: PostgresSourceManagementRepository | None = None
        self._scheduling_repository: PostgresWorkItemSchedulingRepository | None = None

    async def start(self) -> None:
        self._ensure_not_closed()
        if not self._started:
            await self._transaction.start()
            self._started = True

    @property
    def saga_state_repository(self) -> KnowledgeExtractionSagaStateRepositoryPort:
        self._ensure_started()
        if self._saga_repository is None:
            self._saga_repository = PostgresKnowledgeExtractionSagaStateRepository(
                self._connection,
            )
        return self._saga_repository

    @property
    def command_log(self) -> KnowledgeExtractionCommandLogPort:
        return cast(KnowledgeExtractionCommandLogPort, self.saga_state_repository)

    @property
    def event_cursor(self) -> KnowledgeExtractionEventCursorPort:
        return cast(KnowledgeExtractionEventCursorPort, self.saga_state_repository)

    @property
    def command_emitter(self) -> KnowledgeExtractionCommandEmitterPort:
        self._ensure_started()
        return self._command_emitter

    @property
    def source_management_repository(self) -> SourceManagementRepositoryPort:
        self._ensure_started()
        if self._source_repository is None:
            self._source_repository = PostgresSourceManagementRepository(
                self._connection,
            )
        return self._source_repository

    @property
    def work_item_scheduling_repository(self) -> WorkItemSchedulingRepositoryPort:
        self._ensure_started()
        if self._scheduling_repository is None:
            self._scheduling_repository = PostgresWorkItemSchedulingRepository(
                self._connection,
            )
        return self._scheduling_repository

    async def commit(self) -> None:
        self._ensure_not_closed()
        if not self._started:
            raise RuntimeError("cannot commit before transaction start")
        await self._transaction.commit()
        self._closed = True

    async def rollback(self) -> None:
        self._ensure_not_closed()
        if self._started:
            await self._transaction.rollback()
        self._closed = True

    def _ensure_started(self) -> None:
        self._ensure_not_closed()
        if not self._started:
            raise RuntimeError(
                "PostgresKnowledgeExtractionSagaReconcileUnitOfWork.start() must be awaited before use"
            )

    def _ensure_not_closed(self) -> None:
        if self._closed:
            raise RuntimeError(
                "PostgresKnowledgeExtractionSagaReconcileUnitOfWork is already closed",
            )

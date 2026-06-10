from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga import (
    KnowledgeExtractionSaga,
    ReconcileKnowledgeExtractionSagaCommand,
    ReconcileKnowledgeExtractionSagaResult,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    KnowledgeExtractionSourcePhaseReconciler,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_reconcile_unit_of_work import (
    PostgresKnowledgeExtractionSagaReconcileUnitOfWork,
)


class _AsyncKnowledgeExtractionSagaReconcilePoolLike(Protocol):
    async def acquire(self) -> object: ...
    async def release(self, connection: object) -> None: ...


class KnowledgeExtractionSagaReconcileRunner:
    def __init__(
        self,
        *,
        pool: _AsyncKnowledgeExtractionSagaReconcilePoolLike,
        command_emitter: KnowledgeExtractionCommandEmitterPort,
        source_phase_reconciler: KnowledgeExtractionSourcePhaseReconciler | None = None,
    ) -> None:
        self._pool = pool
        self._command_emitter = command_emitter
        self._source_phase_reconciler = source_phase_reconciler

    async def execute(
        self,
        command: ReconcileKnowledgeExtractionSagaCommand,
    ) -> ReconcileKnowledgeExtractionSagaResult:
        connection = await self._pool.acquire()
        try:
            unit_of_work = PostgresKnowledgeExtractionSagaReconcileUnitOfWork(
                cast(asyncpg.Connection, connection),
                command_emitter=self._command_emitter,
            )
            await unit_of_work.start()
            saga = KnowledgeExtractionSaga(
                unit_of_work=unit_of_work,
                source_phase_reconciler=self._source_phase_reconciler,
            )
            return await saga.reconcile(command)
        finally:
            await self._pool.release(connection)


def make_knowledge_extraction_saga_reconcile_runner(
    *,
    pool: object,
    command_emitter: KnowledgeExtractionCommandEmitterPort,
    source_phase_reconciler: KnowledgeExtractionSourcePhaseReconciler | None = None,
) -> KnowledgeExtractionSagaReconcileRunner:
    return KnowledgeExtractionSagaReconcileRunner(
        pool=cast(_AsyncKnowledgeExtractionSagaReconcilePoolLike, pool),
        command_emitter=command_emitter,
        source_phase_reconciler=source_phase_reconciler,
    )

from __future__ import annotations

from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)


class KnowledgeExtractionSagaReconcileUnitOfWorkPort(Protocol):
    @property
    def saga_state_repository(self) -> KnowledgeExtractionSagaStateRepositoryPort: ...

    @property
    def command_log(self) -> KnowledgeExtractionCommandLogPort: ...

    @property
    def event_cursor(self) -> KnowledgeExtractionEventCursorPort: ...

    @property
    def command_emitter(self) -> KnowledgeExtractionCommandEmitterPort: ...

    @property
    def source_management_repository(self) -> SourceManagementRepositoryPort: ...

    @property
    def work_item_scheduling_repository(self) -> WorkItemSchedulingRepositoryPort: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...

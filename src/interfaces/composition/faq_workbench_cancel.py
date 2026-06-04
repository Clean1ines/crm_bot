from __future__ import annotations

from typing import Callable, Protocol, cast

import asyncpg

from src.application.workbench_commands.cancel_processing import (
    WorkbenchCancelProcessingCommand,
    WorkbenchCancelProcessingNotFoundError,
    WorkbenchCancelProcessingRejectedError,
    WorkbenchCancelProcessingService,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


class WorkbenchCancelDbPool(Protocol):
    def acquire(self): ...


async def cancel_workbench_processing(
    *,
    pool: WorkbenchCancelDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = _workbench_repository(connection)
        service = WorkbenchCancelProcessingService(repository)
        result = await service.cancel_processing(
            WorkbenchCancelProcessingCommand(
                project_id=project_id,
                document_id=document_id,
            )
        )
        return result.to_dict()


__all__ = [
    "WorkbenchCancelProcessingNotFoundError",
    "WorkbenchCancelProcessingRejectedError",
    "cancel_workbench_processing",
]


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)

from __future__ import annotations

from typing import Callable, Protocol, cast

import asyncpg

from src.application.workbench_commands.clear_project import (
    WorkbenchProjectClearCommand,
    WorkbenchProjectClearRejectedError,
    WorkbenchProjectClearRepositoryPort,
    WorkbenchProjectClearService,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


class WorkbenchProjectClearDbPool(Protocol):
    def acquire(self): ...


async def clear_workbench_project(
    *,
    pool: WorkbenchProjectClearDbPool,
    project_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = _workbench_repository(connection)
        service = WorkbenchProjectClearService(
            cast(WorkbenchProjectClearRepositoryPort, repository)
        )
        result = await service.clear_project(
            WorkbenchProjectClearCommand(project_id=project_id)
        )
        return result.to_dict()


__all__ = [
    "WorkbenchProjectClearRejectedError",
    "clear_workbench_project",
]


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)

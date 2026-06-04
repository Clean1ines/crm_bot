from __future__ import annotations

from typing import Callable, Protocol, cast

import asyncpg

from src.application.workbench_commands.delete_document import (
    WorkbenchDocumentDeleteCommand,
    WorkbenchDocumentDeleteNotFoundError,
    WorkbenchDocumentDeleteRepositoryPort,
    WorkbenchDocumentDeleteRejectedError,
    WorkbenchDocumentDeleteService,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


class WorkbenchDocumentDeleteDbPool(Protocol):
    def acquire(self): ...


async def delete_workbench_document(
    *,
    pool: WorkbenchDocumentDeleteDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = _workbench_repository(connection)
        service = WorkbenchDocumentDeleteService(
            cast(WorkbenchDocumentDeleteRepositoryPort, repository)
        )
        result = await service.delete_document(
            WorkbenchDocumentDeleteCommand(
                project_id=project_id,
                document_id=document_id,
            )
        )
        return result.to_dict()


__all__ = [
    "WorkbenchDocumentDeleteNotFoundError",
    "WorkbenchDocumentDeleteRejectedError",
    "delete_workbench_document",
]


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)

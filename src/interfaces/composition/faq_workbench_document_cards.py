from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_observability.document_cards import (
    WorkbenchDocumentListReadService,
)
from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityRepository,
)


class WorkbenchDocumentCardsDbPool(Protocol):
    async def acquire(self): ...


async def list_workbench_document_cards(
    *,
    pool: WorkbenchDocumentCardsDbPool,
    project_id: str,
    limit: int,
    offset: int,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = WorkbenchObservabilityRepository(connection)
        service = WorkbenchDocumentListReadService(repository)
        return await service.list_documents(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )


__all__ = ["list_workbench_document_cards"]

from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench.document_card_projection import (
    with_workbench_document_card_views,
)
from src.application.workbench_observability.document_list import (
    WorkbenchDocumentListReadService,
)
from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityRepository,
)


class WorkbenchDocumentsDbPool(Protocol):
    async def acquire(self): ...


async def fetch_workbench_documents(
    *,
    pool: WorkbenchDocumentsDbPool,
    project_id: str,
    limit: int,
    offset: int,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = WorkbenchObservabilityRepository(connection)
        service = WorkbenchDocumentListReadService(repository)
        payload = await service.list_documents(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
        return cast(dict[str, object], with_workbench_document_card_views(payload))


__all__ = ["fetch_workbench_documents"]

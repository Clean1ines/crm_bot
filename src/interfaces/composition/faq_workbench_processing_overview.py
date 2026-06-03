from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_observability.processing_overview import (
    WorkbenchProcessingOverviewReadService,
)
from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityRepository,
)


class WorkbenchProcessingOverviewDbPool(Protocol):
    async def acquire(self): ...


async def fetch_workbench_processing_overview(
    *,
    pool: WorkbenchProcessingOverviewDbPool,
    project_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = WorkbenchObservabilityRepository(connection)
        service = WorkbenchProcessingOverviewReadService(repository)
        return await service.fetch_processing_overview(project_id=project_id)


__all__ = ["fetch_workbench_processing_overview"]

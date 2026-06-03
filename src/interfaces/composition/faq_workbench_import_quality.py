from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_observability.import_quality import (
    WorkbenchImportQualityNotFoundError,
    WorkbenchImportQualityReadService,
)
from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityRepository,
)


class WorkbenchImportQualityDbPool(Protocol):
    async def acquire(self): ...


async def fetch_workbench_import_quality_report(
    *,
    pool: WorkbenchImportQualityDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = WorkbenchObservabilityRepository(connection)
        service = WorkbenchImportQualityReadService(repository)
        return await service.fetch_import_quality_report(
            project_id=project_id,
            document_id=document_id,
        )


__all__ = [
    "WorkbenchImportQualityNotFoundError",
    "fetch_workbench_import_quality_report",
]

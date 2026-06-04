from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_commands.surface_curation import (
    SurfaceCurationService,
)
from src.infrastructure.db.workbench_surface_curation_repository import (
    WorkbenchSurfaceCurationRepository,
)


class WorkbenchSurfaceCurationDbPool(Protocol):
    async def acquire(self): ...


async def make_surface_curation_service(
    pool: WorkbenchSurfaceCurationDbPool,
) -> SurfaceCurationService:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = WorkbenchSurfaceCurationRepository(connection)
        return SurfaceCurationService(repository)


__all__ = ["make_surface_curation_service"]

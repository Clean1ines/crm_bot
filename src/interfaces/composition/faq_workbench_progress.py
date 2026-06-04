from __future__ import annotations

from src.application.workbench_observability.progress import (
    WorkbenchProgressNotFoundError,
    WorkbenchProgressReadService,
)
from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityDbPool,
    WorkbenchObservabilityRepository,
)


async def fetch_workbench_progress(
    *,
    pool: WorkbenchObservabilityDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    repository = WorkbenchObservabilityRepository(pool)
    service = WorkbenchProgressReadService(repository)
    return await service.get_progress(
        project_id=project_id,
        document_id=document_id,
    )


__all__ = ["WorkbenchProgressNotFoundError", "fetch_workbench_progress"]

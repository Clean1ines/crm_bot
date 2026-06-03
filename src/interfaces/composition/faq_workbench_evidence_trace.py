from __future__ import annotations

from typing import Protocol, cast

import asyncpg

from src.application.workbench_observability.evidence_trace import (
    WorkbenchEvidenceTraceNotFoundError,
    WorkbenchEvidenceTraceReadService,
)
from src.infrastructure.db.workbench_observability_repository import (
    WorkbenchObservabilityRepository,
)


class WorkbenchEvidenceTraceDbPool(Protocol):
    async def acquire(self): ...


async def fetch_workbench_evidence_trace(
    *,
    pool: WorkbenchEvidenceTraceDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = WorkbenchObservabilityRepository(connection)
        service = WorkbenchEvidenceTraceReadService(repository)
        return await service.fetch_document_evidence_trace(
            project_id=project_id,
            document_id=document_id,
        )


__all__ = [
    "WorkbenchEvidenceTraceNotFoundError",
    "fetch_workbench_evidence_trace",
]

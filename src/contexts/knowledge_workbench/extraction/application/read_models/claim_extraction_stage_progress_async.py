from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageProgress,
    ClaimExtractionStageProgressQuery,
    ClaimExtractionStageProgressQueryPort,
    ClaimExtractionStageProgressReadModel,
)


class AsyncClaimExtractionStageProgressQueryPort(Protocol):
    async def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]: ...

    async def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int: ...


class AsyncClaimExtractionStageProgressReadModel:
    def __init__(
        self, *, query_port: AsyncClaimExtractionStageProgressQueryPort
    ) -> None:
        self._query_port = query_port

    async def execute(
        self,
        query: ClaimExtractionStageProgressQuery,
    ) -> ClaimExtractionStageProgress:
        work_items = await self._query_port.load_work_items(
            workflow_run_id=query.workflow_run_id,
            stage_run_id=query.stage_run_id,
        )
        artifacts_count = await self._query_port.count_artifacts(
            workflow_run_id=query.workflow_run_id,
            stage_run_id=query.stage_run_id,
        )
        return ClaimExtractionStageProgressReadModel(
            query_port=_LoadedClaimExtractionStageProgressQueryPort(
                work_items=work_items,
                artifacts_count=artifacts_count,
            ),
        ).execute(query)


@dataclass(frozen=True, slots=True)
class _LoadedClaimExtractionStageProgressQueryPort(
    ClaimExtractionStageProgressQueryPort
):
    work_items: tuple[WorkItem, ...]
    artifacts_count: int

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        return self.work_items

    def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int:
        return self.artifacts_count

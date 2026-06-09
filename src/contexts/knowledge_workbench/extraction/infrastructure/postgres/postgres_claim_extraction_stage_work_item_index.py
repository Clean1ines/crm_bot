from __future__ import annotations

from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem


class AsyncStageWorkItemIndexConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> object: ...


class PostgresClaimExtractionStageWorkItemIndex:
    def __init__(self, connection: AsyncStageWorkItemIndexConnectionLike) -> None:
        self._connection = connection

    async def save_stage_work_item(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
        work_item: WorkItem,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO claim_extraction_stage_work_items (
                workflow_run_id,
                stage_run_id,
                work_item_id
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (workflow_run_id, stage_run_id, work_item_id) DO NOTHING
            """,
            workflow_run_id,
            stage_run_id,
            work_item.work_item_id,
        )

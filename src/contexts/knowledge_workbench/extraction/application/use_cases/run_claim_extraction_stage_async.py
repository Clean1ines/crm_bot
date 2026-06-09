from __future__ import annotations

from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import (
    CreateExtractionWorkItems,
    CreateExtractionWorkItemsCommand,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage import (
    ClaimExtractionStageReadiness,
    RunClaimExtractionStageCommand,
    RunClaimExtractionStageResult,
    claim_extraction_stage_readiness,
)


class AsyncClaimExtractionWorkItemUnitOfWorkPort(Protocol):
    async def save_work_item(self, item: WorkItem) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class AsyncClaimExtractionStageWorkItemIndexPort(Protocol):
    async def save_stage_work_item(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
        work_item: WorkItem,
    ) -> None: ...


class AsyncClaimExtractionWorkItemCreatorPort(Protocol):
    def execute(self, command: CreateExtractionWorkItemsCommand) -> object: ...


class RunClaimExtractionStageAsync:
    """Async fan-out entry point for production PostgreSQL adapters."""

    def __init__(
        self,
        *,
        unit_of_work: AsyncClaimExtractionWorkItemUnitOfWorkPort,
        stage_work_item_index: AsyncClaimExtractionStageWorkItemIndexPort,
        work_item_creator: AsyncClaimExtractionWorkItemCreatorPort | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._stage_work_item_index = stage_work_item_index
        self._work_item_creator = work_item_creator or CreateExtractionWorkItems()

    async def execute(
        self,
        command: RunClaimExtractionStageCommand,
    ) -> RunClaimExtractionStageResult:
        created = self._work_item_creator.execute(
            CreateExtractionWorkItemsCommand(
                source_units=command.source_units,
                prompt_id=command.prompt_id,
            ),
        )
        work_items = _created_work_items(created)

        try:
            for item in work_items:
                await self._unit_of_work.save_work_item(item)
                await self._stage_work_item_index.save_stage_work_item(
                    workflow_run_id=command.workflow_run_id,
                    stage_run_id=command.stage_run_id,
                    work_item=item,
                )
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise

        return RunClaimExtractionStageResult(
            work_items=work_items,
            readiness=claim_extraction_stage_readiness(work_items),
        )


def _created_work_items(created: object) -> tuple[WorkItem, ...]:
    work_items = getattr(created, "work_items", None)
    if not isinstance(work_items, tuple):
        raise TypeError("work_item_creator result must expose tuple work_items")
    if not all(isinstance(item, WorkItem) for item in work_items):
        raise TypeError("work_item_creator work_items must contain only WorkItem")
    if not work_items:
        raise ValueError("work_item_creator returned no work items")
    return work_items

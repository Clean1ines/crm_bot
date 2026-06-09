from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_work_item_index import (
    PostgresClaimExtractionStageWorkItemIndex,
)


@dataclass(slots=True)
class FakeConnection:
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        return "OK"


@pytest.mark.asyncio
async def test_save_stage_work_item_builds_idempotent_stage_index_sql() -> None:
    connection = FakeConnection()
    index = PostgresClaimExtractionStageWorkItemIndex(connection)

    await index.save_stage_work_item(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        work_item=WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        ),
    )

    sql, args = connection.calls[0]
    assert "INSERT INTO claim_extraction_stage_work_items" in sql
    assert "ON CONFLICT (workflow_run_id, stage_run_id, work_item_id) DO NOTHING" in sql
    assert args == ("workflow-1", "stage-1", "work-1")

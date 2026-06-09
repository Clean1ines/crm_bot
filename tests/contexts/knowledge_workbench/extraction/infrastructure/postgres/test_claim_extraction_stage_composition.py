from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_composition import (
    make_postgres_claim_extraction_stage_runner,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_work_item_index import (
    PostgresClaimExtractionStageWorkItemIndex,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_work_item_unit_of_work import (
    PostgresClaimExtractionWorkItemUnitOfWork,
)


class FakeConnection:
    def transaction(self) -> object:
        return object()

    async def execute(self, query: str, *args: object) -> object:
        return "OK"


def test_postgres_claim_extraction_stage_composition_builds_async_runner() -> None:
    runner = make_postgres_claim_extraction_stage_runner(FakeConnection())

    assert isinstance(runner, RunClaimExtractionStageAsync)
    assert isinstance(runner._unit_of_work, PostgresClaimExtractionWorkItemUnitOfWork)
    assert isinstance(runner._stage_work_item_index, PostgresClaimExtractionStageWorkItemIndex)

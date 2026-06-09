from __future__ import annotations

from object import object

from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_work_item_index import (
    PostgresClaimExtractionStageWorkItemIndex,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_work_item_unit_of_work import (
    PostgresClaimExtractionWorkItemUnitOfWork,
)


def make_postgres_claim_extraction_stage_runner(connection: object) -> RunClaimExtractionStageAsync:
    return RunClaimExtractionStageAsync(
        unit_of_work=PostgresClaimExtractionWorkItemUnitOfWork(connection),
        stage_work_item_index=PostgresClaimExtractionStageWorkItemIndex(connection),
    )

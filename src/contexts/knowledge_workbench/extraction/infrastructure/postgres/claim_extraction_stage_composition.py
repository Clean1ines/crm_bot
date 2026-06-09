from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_work_item_index import (
    AsyncStageWorkItemIndexConnectionLike,
    PostgresClaimExtractionStageWorkItemIndex,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_work_item_unit_of_work import (
    AsyncConnectionLike,
    PostgresClaimExtractionWorkItemUnitOfWork,
)


class ClaimExtractionStageConnectionLike(
    AsyncConnectionLike,
    AsyncStageWorkItemIndexConnectionLike,
    Protocol,
):
    pass


def make_postgres_claim_extraction_stage_runner(
    connection: ClaimExtractionStageConnectionLike,
) -> RunClaimExtractionStageAsync:
    return RunClaimExtractionStageAsync(
        unit_of_work=PostgresClaimExtractionWorkItemUnitOfWork(connection),
        stage_work_item_index=PostgresClaimExtractionStageWorkItemIndex(connection),
    )

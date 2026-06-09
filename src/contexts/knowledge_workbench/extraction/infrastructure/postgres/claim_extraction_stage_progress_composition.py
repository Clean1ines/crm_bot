from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress_async import (
    AsyncClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_progress_query import (
    PostgresClaimExtractionStageProgressQuery,
)


def make_postgres_claim_extraction_stage_progress_reader(
    connection: object,
) -> AsyncClaimExtractionStageProgressReadModel:
    return AsyncClaimExtractionStageProgressReadModel(
        query_port=PostgresClaimExtractionStageProgressQuery(connection),
    )

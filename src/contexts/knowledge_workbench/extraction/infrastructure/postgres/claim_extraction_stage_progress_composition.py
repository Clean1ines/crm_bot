from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_progress_query import (
    PostgresClaimExtractionStageProgressQuery,
)


def make_postgres_claim_extraction_stage_progress_reader(
    connection: object,
) -> ClaimExtractionStageProgressReadModel:
    return ClaimExtractionStageProgressReadModel(
        query_port=PostgresClaimExtractionStageProgressQuery(connection),
    )

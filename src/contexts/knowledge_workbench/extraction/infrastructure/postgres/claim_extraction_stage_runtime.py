from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_composition import (
    make_postgres_claim_extraction_stage_runner,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_progress_composition import (
    make_postgres_claim_extraction_stage_progress_reader,
)


@dataclass(frozen=True, slots=True)
class ClaimExtractionStagePostgresRuntime:
    runner: RunClaimExtractionStageAsync
    progress_reader: ClaimExtractionStageProgressReadModel


def make_claim_extraction_stage_postgres_runtime(
    connection: object,
) -> ClaimExtractionStagePostgresRuntime:
    return ClaimExtractionStagePostgresRuntime(
        runner=make_postgres_claim_extraction_stage_runner(connection),
        progress_reader=make_postgres_claim_extraction_stage_progress_reader(connection),
    )

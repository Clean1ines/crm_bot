from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress_async import (
    AsyncClaimExtractionStageProgressReadModel,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_composition import (
    ClaimExtractionStageConnectionLike,
    make_postgres_claim_extraction_stage_runner,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_progress_composition import (
    AsyncStageProgressConnectionLike,
    make_postgres_claim_extraction_stage_progress_reader,
)


class ClaimExtractionStagePostgresConnectionLike(
    ClaimExtractionStageConnectionLike,
    AsyncStageProgressConnectionLike,
    Protocol,
):
    pass


@dataclass(frozen=True, slots=True)
class ClaimExtractionStagePostgresRuntime:
    runner: RunClaimExtractionStageAsync
    progress_reader: AsyncClaimExtractionStageProgressReadModel


def make_claim_extraction_stage_postgres_runtime(
    connection: ClaimExtractionStagePostgresConnectionLike,
) -> ClaimExtractionStagePostgresRuntime:
    return ClaimExtractionStagePostgresRuntime(
        runner=make_postgres_claim_extraction_stage_runner(connection),
        progress_reader=make_postgres_claim_extraction_stage_progress_reader(
            connection
        ),
    )

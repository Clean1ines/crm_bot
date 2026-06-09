from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
)
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
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.draft_claim_observation_application_composition import (
    DraftClaimObservationApplicationConnectionLike,
    make_postgres_apply_draft_claim_observation_artifact,
)


class ClaimExtractionStagePostgresConnectionLike(
    ClaimExtractionStageConnectionLike,
    AsyncStageProgressConnectionLike,
    DraftClaimObservationApplicationConnectionLike,
    Protocol,
):
    pass


@dataclass(frozen=True, slots=True)
class ClaimExtractionStagePostgresRuntime:
    runner: RunClaimExtractionStageAsync
    progress_reader: AsyncClaimExtractionStageProgressReadModel
    apply_draft_claim_observation_artifact: ApplyDraftClaimObservationArtifactAsync


def make_claim_extraction_stage_postgres_runtime(
    connection: ClaimExtractionStagePostgresConnectionLike,
) -> ClaimExtractionStagePostgresRuntime:
    return ClaimExtractionStagePostgresRuntime(
        runner=make_postgres_claim_extraction_stage_runner(connection),
        progress_reader=make_postgres_claim_extraction_stage_progress_reader(
            connection
        ),
        apply_draft_claim_observation_artifact=(
            make_postgres_apply_draft_claim_observation_artifact(connection)
        ),
    )

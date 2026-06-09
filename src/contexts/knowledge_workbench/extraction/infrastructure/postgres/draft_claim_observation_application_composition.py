from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_artifact_parser import (
    DraftClaimObservationArtifactParser,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_observation_provenance_candidate_builder import (
    DraftClaimObservationProvenanceCandidateBuilder,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.apply_draft_claim_observation_artifact import (
    ApplyDraftClaimObservationArtifactAsync,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_application_unit_of_work import (
    AsyncConnectionLike,
    PostgresDraftClaimObservationApplicationUnitOfWork,
)


class DraftClaimObservationApplicationConnectionLike(
    AsyncConnectionLike,
    Protocol,
):
    pass


def make_postgres_apply_draft_claim_observation_artifact(
    connection: DraftClaimObservationApplicationConnectionLike,
) -> ApplyDraftClaimObservationArtifactAsync:
    return ApplyDraftClaimObservationArtifactAsync(
        parser=DraftClaimObservationArtifactParser(),
        unit_of_work=PostgresDraftClaimObservationApplicationUnitOfWork(connection),
        provenance_candidate_builder=DraftClaimObservationProvenanceCandidateBuilder(),
    )

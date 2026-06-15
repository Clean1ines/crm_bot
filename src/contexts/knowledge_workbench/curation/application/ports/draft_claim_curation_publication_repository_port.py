from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_publication import (
    DraftClaimCurationPublicationCandidate,
    DraftClaimCurationPublicationResult,
)


class DraftClaimCurationPublicationRepositoryPort(Protocol):
    async def publish_curated_claims(
        self,
        *,
        publication: DraftClaimCurationPublicationCandidate,
    ) -> DraftClaimCurationPublicationResult: ...

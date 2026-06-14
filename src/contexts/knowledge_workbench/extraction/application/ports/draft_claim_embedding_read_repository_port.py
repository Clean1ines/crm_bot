from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)


class DraftClaimEmbeddingReadRepositoryPort(Protocol):
    async def list_unembedded_claim_observations_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
        limit: int,
    ) -> tuple[DraftClaimObservation, ...]: ...

from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_cluster_preview import (
    DraftClaimClusterPreview,
    DraftClaimClusterPreviewBuildResult,
)


class DraftClaimClusterPreviewRepositoryPort(Protocol):
    async def save_preview(
        self,
        preview: DraftClaimClusterPreview,
    ) -> DraftClaimClusterPreviewBuildResult: ...

    async def load_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimClusterPreview | None: ...

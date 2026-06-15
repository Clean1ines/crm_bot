from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceItem,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)


class DraftClaimCurationItemExclusionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SetDraftClaimCurationItemExcluded:
    curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort

    async def execute(
        self,
        *,
        workflow_run_id: str,
        item_ref: str,
        excluded: bool,
        exclusion_reason: str | None,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem:
        snapshot = (
            await self.curation_workspace_repository.get_workspace_by_workflow_run_id(
                workflow_run_id=workflow_run_id,
            )
        )
        if snapshot is None:
            raise DraftClaimCurationItemExclusionError(
                "curation workspace was not found"
            )
        if not any(item.item_ref == item_ref for item in snapshot.items):
            raise DraftClaimCurationItemExclusionError(
                "curation workspace item was not found"
            )
        reason = exclusion_reason.strip() if isinstance(exclusion_reason, str) else None
        if reason == "":
            reason = None
        return await self.curation_workspace_repository.set_item_excluded(
            item_ref=item_ref,
            excluded=excluded,
            exclusion_reason=reason,
            updated_at=updated_at,
        )

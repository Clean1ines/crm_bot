from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceItem,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)


class DraftClaimCurationItemUpdateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UpdateDraftClaimCurationItem:
    curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort

    async def execute(
        self,
        *,
        workflow_run_id: str,
        item_ref: str,
        updates: Mapping[str, object],
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem:
        snapshot = (
            await self.curation_workspace_repository.get_workspace_by_workflow_run_id(
                workflow_run_id=workflow_run_id,
            )
        )
        if snapshot is None:
            raise DraftClaimCurationItemUpdateError("curation workspace was not found")
        item = _item_from_snapshot(snapshot.items, item_ref)
        editable_payload = item.editable_payload.with_editable_updates(updates)
        return await self.curation_workspace_repository.replace_item_editable_payload(
            item_ref=item_ref,
            editable_payload=editable_payload,
            updated_at=updated_at,
        )


def _item_from_snapshot(
    items: tuple[DraftClaimCurationWorkspaceItem, ...],
    item_ref: str,
) -> DraftClaimCurationWorkspaceItem:
    for item in items:
        if item.item_ref == item_ref:
            return item
    raise DraftClaimCurationItemUpdateError("curation workspace item was not found")

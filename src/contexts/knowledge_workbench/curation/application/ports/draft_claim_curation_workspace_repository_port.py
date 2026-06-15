from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
)


class DraftClaimCurationWorkspaceRepositoryPort(Protocol):
    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None: ...

    async def get_item(
        self,
        *,
        item_ref: str,
    ) -> DraftClaimCurationWorkspaceItem | None: ...

    async def create_workspace(
        self,
        *,
        workspace: DraftClaimCurationWorkspace,
        items: tuple[DraftClaimCurationWorkspaceItem, ...],
    ) -> DraftClaimCurationWorkspaceSnapshot: ...

    async def list_items(
        self,
        *,
        workspace_ref: str,
    ) -> tuple[DraftClaimCurationWorkspaceItem, ...]: ...

    async def replace_item_editable_payload(
        self,
        *,
        item_ref: str,
        editable_payload: DraftClaimCurationItemEditablePayload,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem: ...

    async def set_item_excluded(
        self,
        *,
        item_ref: str,
        excluded: bool,
        exclusion_reason: str | None,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem: ...

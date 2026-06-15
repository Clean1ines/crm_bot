from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
    DraftClaimCurationWorkspaceStatus,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.set_draft_claim_curation_item_excluded import (
    SetDraftClaimCurationItemExcluded,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.update_draft_claim_curation_item import (
    UpdateDraftClaimCurationItem,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _payload() -> dict[str, object]:
    return {
        "key": "refund_support",
        "claim": "Product supports refunds.",
        "claim_kind": "capability",
        "granularity": "atomic",
        "source_claim_refs": ["claim-a"],
        "triples": [
            {
                "subject": "Product",
                "predicate": "has_capability",
                "object": "refunds",
                "qualifiers": [],
            }
        ],
        "merge_decision": "merged",
        "possible_questions": ["Q1"],
        "exclusion_scope": "",
        "evidence_block": "E1",
    }


def _item() -> DraftClaimCurationWorkspaceItem:
    payload = DraftClaimCurationItemEditablePayload.from_payload(_payload())
    return DraftClaimCurationWorkspaceItem(
        item_ref="item-1",
        workspace_ref="workspace-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        compacted_node_ref="compacted-1",
        source_claim_refs=("claim-a",),
        original_payload=payload,
        editable_payload=payload,
        excluded=False,
        exclusion_reason=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _snapshot(
    item: DraftClaimCurationWorkspaceItem,
) -> DraftClaimCurationWorkspaceSnapshot:
    return DraftClaimCurationWorkspaceSnapshot(
        workspace=DraftClaimCurationWorkspace(
            workspace_ref="workspace-1",
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref=None,
            status=DraftClaimCurationWorkspaceStatus.DRAFT,
            created_at=_now(),
            updated_at=_now(),
        ),
        items=(item,),
    )


@dataclass(slots=True)
class FakeRepository:
    item: DraftClaimCurationWorkspaceItem

    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None:
        del workflow_run_id
        return _snapshot(self.item)

    async def replace_item_editable_payload(
        self,
        *,
        item_ref: str,
        editable_payload: DraftClaimCurationItemEditablePayload,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem:
        assert item_ref == self.item.item_ref
        self.item = DraftClaimCurationWorkspaceItem(
            item_ref=self.item.item_ref,
            workspace_ref=self.item.workspace_ref,
            workflow_run_id=self.item.workflow_run_id,
            group_ref=self.item.group_ref,
            compacted_node_ref=self.item.compacted_node_ref,
            source_claim_refs=self.item.source_claim_refs,
            original_payload=self.item.original_payload,
            editable_payload=editable_payload,
            excluded=self.item.excluded,
            exclusion_reason=self.item.exclusion_reason,
            created_at=self.item.created_at,
            updated_at=updated_at,
        )
        return self.item

    async def set_item_excluded(
        self,
        *,
        item_ref: str,
        excluded: bool,
        exclusion_reason: str | None,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem:
        assert item_ref == self.item.item_ref
        self.item = DraftClaimCurationWorkspaceItem(
            item_ref=self.item.item_ref,
            workspace_ref=self.item.workspace_ref,
            workflow_run_id=self.item.workflow_run_id,
            group_ref=self.item.group_ref,
            compacted_node_ref=self.item.compacted_node_ref,
            source_claim_refs=self.item.source_claim_refs,
            original_payload=self.item.original_payload,
            editable_payload=self.item.editable_payload,
            excluded=excluded,
            exclusion_reason=exclusion_reason,
            created_at=self.item.created_at,
            updated_at=updated_at,
        )
        return self.item


@pytest.mark.asyncio
async def test_update_item_allows_only_editable_publishable_fields() -> None:
    updated = await UpdateDraftClaimCurationItem(FakeRepository(item=_item())).execute(
        workflow_run_id="workflow-1",
        item_ref="item-1",
        updates={
            "claim": "Product supports managed refunds.",
            "possible_questions": ["Q1", " Q2 ", "Q2", " "],
            "exclusion_scope": "not marketplace refunds",
            "evidence_block": "Updated evidence",
        },
        updated_at=_now(),
    )

    payload = updated.editable_payload.to_json_dict()
    assert payload["claim"] == "Product supports managed refunds."
    assert payload["possible_questions"] == ["Q1", "Q2"]
    assert payload["exclusion_scope"] == "not marketplace refunds"
    assert payload["evidence_block"] == "Updated evidence"
    assert payload["source_claim_refs"] == ["claim-a"]
    assert payload["merge_decision"] == "merged"


@pytest.mark.asyncio
async def test_update_item_rejects_source_claim_refs_edit() -> None:
    with pytest.raises(ValueError, match="non-editable payload fields"):
        await UpdateDraftClaimCurationItem(FakeRepository(item=_item())).execute(
            workflow_run_id="workflow-1",
            item_ref="item-1",
            updates={"source_claim_refs": ["claim-x"]},
            updated_at=_now(),
        )


@pytest.mark.asyncio
async def test_exclude_and_include_item() -> None:
    repository = FakeRepository(item=_item())

    excluded = await SetDraftClaimCurationItemExcluded(repository).execute(
        workflow_run_id="workflow-1",
        item_ref="item-1",
        excluded=True,
        exclusion_reason="duplicate",
        updated_at=_now(),
    )
    assert excluded.excluded is True
    assert excluded.exclusion_reason == "duplicate"

    included = await SetDraftClaimCurationItemExcluded(repository).execute(
        workflow_run_id="workflow-1",
        item_ref="item-1",
        excluded=False,
        exclusion_reason=None,
        updated_at=_now(),
    )
    assert included.excluded is False
    assert included.exclusion_reason is None

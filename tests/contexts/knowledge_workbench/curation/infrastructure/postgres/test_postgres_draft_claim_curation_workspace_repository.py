from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json

import pytest

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceStatus,
)
from src.contexts.knowledge_workbench.curation.infrastructure.postgres.postgres_draft_claim_curation_workspace_repository import (
    PostgresDraftClaimCurationWorkspaceRepository,
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
        "triples": [],
        "merge_decision": "merged",
        "possible_questions": ["Q1"],
        "exclusion_scope": "",
        "evidence_block": "E1",
    }


def _workspace() -> DraftClaimCurationWorkspace:
    return DraftClaimCurationWorkspace(
        workspace_ref="workspace-1",
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref=None,
        status=DraftClaimCurationWorkspaceStatus.DRAFT,
        created_at=_now(),
        updated_at=_now(),
    )


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


@dataclass(slots=True)
class FakeConnection:
    workspaces: dict[str, dict[str, object]] = field(default_factory=dict)
    items: dict[str, dict[str, object]] = field(default_factory=dict)

    async def execute(self, query: str, *args: object) -> str:
        if "INSERT INTO draft_claim_curation_workspaces" in query:
            workflow_run_id = _str(args[1])
            if workflow_run_id not in self.workspaces:
                self.workspaces[workflow_run_id] = {
                    "workspace_ref": _str(args[0]),
                    "workflow_run_id": workflow_run_id,
                    "project_id": args[2],
                    "source_document_ref": args[3],
                    "status": _str(args[4]),
                    "created_at": args[5],
                    "updated_at": args[6],
                }
            return "INSERT 0 1"
        if "INSERT INTO draft_claim_curation_items" in query:
            compacted_node_ref = _str(args[4])
            if compacted_node_ref not in self.items:
                self.items[compacted_node_ref] = {
                    "item_ref": _str(args[0]),
                    "workspace_ref": _str(args[1]),
                    "workflow_run_id": _str(args[2]),
                    "group_ref": _str(args[3]),
                    "compacted_node_ref": compacted_node_ref,
                    "source_claim_refs": json.loads(_str(args[5])),
                    "original_payload": json.loads(_str(args[6])),
                    "editable_payload": json.loads(_str(args[7])),
                    "excluded": args[8],
                    "exclusion_reason": args[9],
                    "created_at": args[10],
                    "updated_at": args[11],
                }
            return "INSERT 0 1"
        if "UPDATE draft_claim_curation_items" in query and "editable_payload" in query:
            row = self._item_by_ref(_str(args[0]))
            row["editable_payload"] = json.loads(_str(args[1]))
            row["updated_at"] = args[2]
            return "UPDATE 1"
        if "UPDATE draft_claim_curation_items" in query and "excluded" in query:
            row = self._item_by_ref(_str(args[0]))
            row["excluded"] = args[1]
            row["exclusion_reason"] = args[2]
            row["updated_at"] = args[3]
            return "UPDATE 1"
        raise AssertionError(query)

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        if "FROM draft_claim_curation_workspaces" in query:
            return self.workspaces.get(_str(args[0]))
        if "FROM draft_claim_curation_items" in query:
            return self._item_by_ref(_str(args[0]))
        raise AssertionError(query)

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if "FROM draft_claim_curation_items" in query:
            workspace_ref = _str(args[0])
            return [
                row
                for row in self.items.values()
                if row["workspace_ref"] == workspace_ref
            ]
        raise AssertionError(query)

    def _item_by_ref(self, item_ref: str) -> dict[str, object]:
        for row in self.items.values():
            if row["item_ref"] == item_ref:
                return row
        raise KeyError(item_ref)


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be str")
    return value


@pytest.mark.asyncio
async def test_create_workspace_is_idempotent_by_workflow_and_compacted_node() -> None:
    connection = FakeConnection()
    repository = PostgresDraftClaimCurationWorkspaceRepository(connection)

    first = await repository.create_workspace(workspace=_workspace(), items=(_item(),))
    second = await repository.create_workspace(workspace=_workspace(), items=(_item(),))

    assert first.workspace.workflow_run_id == "workflow-1"
    assert len(first.items) == 1
    assert len(second.items) == 1
    assert len(connection.workspaces) == 1
    assert len(connection.items) == 1


@pytest.mark.asyncio
async def test_update_payload_and_exclusion_return_current_item() -> None:
    connection = FakeConnection()
    repository = PostgresDraftClaimCurationWorkspaceRepository(connection)
    await repository.create_workspace(workspace=_workspace(), items=(_item(),))

    updated_payload = DraftClaimCurationItemEditablePayload.from_payload(
        {**_payload(), "claim": "Updated claim."}
    )
    item = await repository.replace_item_editable_payload(
        item_ref="item-1",
        editable_payload=updated_payload,
        updated_at=_now(),
    )
    assert item.editable_payload.to_json_dict()["claim"] == "Updated claim."

    excluded = await repository.set_item_excluded(
        item_ref="item-1",
        excluded=True,
        exclusion_reason="duplicate",
        updated_at=_now(),
    )
    assert excluded.excluded is True
    assert excluded.exclusion_reason == "duplicate"

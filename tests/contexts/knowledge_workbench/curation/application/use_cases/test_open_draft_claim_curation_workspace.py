from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.open_draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceOpenError,
    DraftClaimCurationWorkspaceProjectMismatchError,
    OpenDraftClaimCurationWorkspace,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _payload() -> dict[str, object]:
    return {
        "key": "refund_support",
        "claim": "Product supports refunds.",
        "claim_kind": "capability",
        "granularity": "atomic",
        "source_claim_refs": ["claim-a", "claim-b"],
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


def _node() -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=(
            "compacted:"
            + _workflow_run_id()
            + ":group-1:559cfb86ea804a483bcf8f6b28c8eec0"
        ),
        node_kind=DraftClaimCompactionNodeKind.COMPACTED,
        source_claim_refs=("claim-a", "claim-b"),
        active=True,
        compacted_key="refund_support",
        compacted_claim="Product supports refunds.",
        compacted_payload=_payload(),
    )


@dataclass(slots=True)
class FakeCurationRepository:
    snapshot: DraftClaimCurationWorkspaceSnapshot | None = None
    created_items: list[DraftClaimCurationWorkspaceItem] = field(default_factory=list)

    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None:
        del workflow_run_id
        return self.snapshot

    async def create_workspace(
        self,
        *,
        workspace: DraftClaimCurationWorkspace,
        items: tuple[DraftClaimCurationWorkspaceItem, ...],
    ) -> DraftClaimCurationWorkspaceSnapshot:
        self.created_items.extend(items)
        self.snapshot = DraftClaimCurationWorkspaceSnapshot(
            workspace=workspace,
            items=items,
        )
        return self.snapshot


@dataclass(slots=True)
class FakeCompactionRepository:
    active_raw_count: int = 0
    nodes: tuple[DraftClaimCompactionNode, ...] = (_node(),)

    async def count_active_raw_nodes(self, *, workflow_run_id: str) -> int:
        del workflow_run_id
        return self.active_raw_count

    async def list_final_compacted_nodes_for_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[DraftClaimCompactionNode, ...]:
        del workflow_run_id
        return self.nodes


@pytest.mark.asyncio
async def test_opens_workspace_from_final_enriched_compacted_payloads() -> None:
    snapshot = await OpenDraftClaimCurationWorkspace(
        curation_workspace_repository=FakeCurationRepository(),
        compaction_reduction_state_repository=FakeCompactionRepository(),
    ).execute(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        created_at=_now(),
    )

    assert snapshot.workspace.status.value == "draft"
    assert snapshot.workspace.project_id == "project-1"
    assert len(snapshot.items) == 1
    item = snapshot.items[0]
    assert item.group_ref == "group-1"
    assert item.original_payload.to_json_dict() == _payload()
    assert item.editable_payload.to_json_dict() == _payload()
    assert item.excluded is False


@pytest.mark.asyncio
async def test_open_workspace_is_idempotent_by_workflow_run_id() -> None:
    repository = FakeCurationRepository()
    first = await OpenDraftClaimCurationWorkspace(
        curation_workspace_repository=repository,
        compaction_reduction_state_repository=FakeCompactionRepository(),
    ).execute(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref=None,
        created_at=_now(),
    )

    second = await OpenDraftClaimCurationWorkspace(
        curation_workspace_repository=repository,
        compaction_reduction_state_repository=FakeCompactionRepository(nodes=()),
    ).execute(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref=None,
        created_at=_now(),
    )

    assert second == first
    assert len(repository.created_items) == 1


@pytest.mark.asyncio
async def test_open_workspace_rejects_active_raw_nodes() -> None:
    with pytest.raises(
        DraftClaimCurationWorkspaceOpenError,
        match="active raw nodes remain",
    ):
        await OpenDraftClaimCurationWorkspace(
            curation_workspace_repository=FakeCurationRepository(),
            compaction_reduction_state_repository=FakeCompactionRepository(
                active_raw_count=1
            ),
        ).execute(
            workflow_run_id=_workflow_run_id(),
            project_id="project-1",
            source_document_ref=None,
            created_at=_now(),
        )


@pytest.mark.asyncio
async def test_open_workspace_rejects_missing_compacted_payload() -> None:
    node = DraftClaimCompactionNode(
        node_ref=(
            "compacted:"
            + _workflow_run_id()
            + ":group-1:559cfb86ea804a483bcf8f6b28c8eec0"
        ),
        node_kind=DraftClaimCompactionNodeKind.COMPACTED,
        source_claim_refs=("claim-a",),
        active=True,
    )

    with pytest.raises(
        DraftClaimCurationWorkspaceOpenError,
        match="compacted_payload",
    ):
        await OpenDraftClaimCurationWorkspace(
            curation_workspace_repository=FakeCurationRepository(),
            compaction_reduction_state_repository=FakeCompactionRepository(
                nodes=(node,)
            ),
        ).execute(
            workflow_run_id=_workflow_run_id(),
            project_id="project-1",
            source_document_ref=None,
            created_at=_now(),
        )


@pytest.mark.asyncio
async def test_existing_workspace_with_different_project_id_is_rejected() -> None:
    repository = FakeCurationRepository()
    existing = await OpenDraftClaimCurationWorkspace(
        curation_workspace_repository=repository,
        compaction_reduction_state_repository=FakeCompactionRepository(),
    ).execute(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        created_at=_now(),
    )

    assert existing.workspace.project_id == "project-1"

    with pytest.raises(
        DraftClaimCurationWorkspaceProjectMismatchError,
        match="does not belong to project",
    ):
        await OpenDraftClaimCurationWorkspace(
            curation_workspace_repository=repository,
            compaction_reduction_state_repository=FakeCompactionRepository(nodes=()),
        ).execute(
            workflow_run_id=_workflow_run_id(),
            project_id="project-2",
            source_document_ref="source-document:project-2:abc",
            created_at=_now(),
        )

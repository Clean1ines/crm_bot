from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
    DraftClaimCurationWorkspaceStatus,
    draft_claim_curation_item_ref,
    draft_claim_curation_workspace_ref,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)


class DraftClaimCurationWorkspaceOpenError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenDraftClaimCurationWorkspace:
    curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort
    compaction_reduction_state_repository: (
        DraftClaimCompactionReductionStateRepositoryPort
    )

    async def execute(
        self,
        *,
        workflow_run_id: str,
        project_id: str | None,
        source_document_ref: str | None,
        created_at: datetime,
    ) -> DraftClaimCurationWorkspaceSnapshot:
        existing = (
            await self.curation_workspace_repository.get_workspace_by_workflow_run_id(
                workflow_run_id=workflow_run_id,
            )
        )
        if existing is not None:
            return existing

        active_raw_count = (
            await self.compaction_reduction_state_repository.count_active_raw_nodes(
                workflow_run_id=workflow_run_id,
            )
        )
        if active_raw_count:
            raise DraftClaimCurationWorkspaceOpenError(
                "cannot open curation workspace while active raw nodes remain"
            )

        compacted_nodes = await self.compaction_reduction_state_repository.list_final_compacted_nodes_for_preview(
            workflow_run_id=workflow_run_id,
        )
        if not compacted_nodes:
            raise DraftClaimCurationWorkspaceOpenError(
                "cannot open curation workspace without final compacted nodes"
            )

        workspace_ref = draft_claim_curation_workspace_ref(workflow_run_id)
        workspace = DraftClaimCurationWorkspace(
            workspace_ref=workspace_ref,
            workflow_run_id=workflow_run_id,
            project_id=project_id,
            source_document_ref=source_document_ref,
            status=DraftClaimCurationWorkspaceStatus.DRAFT,
            created_at=created_at,
            updated_at=created_at,
        )
        items = tuple(
            _item_from_compacted_node(
                workspace_ref=workspace_ref,
                workflow_run_id=workflow_run_id,
                node=node,
                created_at=created_at,
            )
            for node in compacted_nodes
        )
        return await self.curation_workspace_repository.create_workspace(
            workspace=workspace,
            items=items,
        )


def _item_from_compacted_node(
    *,
    workspace_ref: str,
    workflow_run_id: str,
    node: DraftClaimCompactionNode,
    created_at: datetime,
) -> DraftClaimCurationWorkspaceItem:
    payload = node.compacted_payload
    if payload is None:
        raise DraftClaimCurationWorkspaceOpenError(
            "compacted node lacks compacted_payload"
        )
    original_payload = DraftClaimCurationItemEditablePayload.from_payload(payload)
    group_ref = _group_ref_from_compacted_node_ref(
        workflow_run_id=workflow_run_id,
        compacted_node_ref=node.node_ref,
    )
    return DraftClaimCurationWorkspaceItem(
        item_ref=draft_claim_curation_item_ref(
            workspace_ref=workspace_ref,
            compacted_node_ref=node.node_ref,
        ),
        workspace_ref=workspace_ref,
        workflow_run_id=workflow_run_id,
        group_ref=group_ref,
        compacted_node_ref=node.node_ref,
        source_claim_refs=original_payload.source_claim_refs,
        original_payload=original_payload,
        editable_payload=original_payload,
        excluded=False,
        exclusion_reason=None,
        created_at=created_at,
        updated_at=created_at,
    )


def _group_ref_from_compacted_node_ref(
    *,
    workflow_run_id: str,
    compacted_node_ref: str,
) -> str:
    prefix = f"compacted:{workflow_run_id}:"
    if not compacted_node_ref.startswith(prefix):
        raise DraftClaimCurationWorkspaceOpenError(
            "compacted node ref does not match workflow_run_id"
        )
    remainder = compacted_node_ref[len(prefix) :]
    group_ref, _, digest = remainder.partition(":")
    if not group_ref or not digest:
        raise DraftClaimCurationWorkspaceOpenError("compacted node ref lacks group_ref")
    return group_ref

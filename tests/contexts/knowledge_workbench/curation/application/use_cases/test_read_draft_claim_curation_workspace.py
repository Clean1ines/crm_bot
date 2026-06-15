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
from src.contexts.knowledge_workbench.curation.application.use_cases.read_draft_claim_curation_workspace import (
    ReadDraftClaimCurationWorkspace,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
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


def _snapshot() -> DraftClaimCurationWorkspaceSnapshot:
    payload = DraftClaimCurationItemEditablePayload.from_payload(_payload())
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
        items=(
            DraftClaimCurationWorkspaceItem(
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
            ),
        ),
    )


@dataclass(slots=True)
class FakeCurationRepository:
    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None:
        del workflow_run_id
        return _snapshot()


@dataclass(slots=True)
class FakeDraftClaimRepository:
    async def list_by_observation_refs(
        self,
        *,
        observation_refs: tuple[str, ...],
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        assert observation_refs == ("claim-a",)
        return (
            DraftClaimObservationReadModel(
                observation_ref="claim-a",
                source_unit_ref="source-unit-1",
                claim="Raw claim.",
                granularity="atomic",
                possible_questions=("Q1",),
                exclusion_scope="",
                evidence_block="E1",
                workflow_run_id="workflow-1",
                stage_run_id=None,
                work_item_id=None,
                work_item_attempt_id=None,
                llm_task_id=None,
                llm_attempt_id=None,
                prompt_id=None,
                prompt_version=None,
                claim_index=0,
                created_at=_now(),
            ),
        )


@dataclass(slots=True)
class FakeSourceRepository:
    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        assert unit_ref == SourceUnitRef("source-unit-1")
        return SourceUnit(
            unit_ref=unit_ref,
            document_ref=SourceDocumentRef("source-document:project-1:abc"),
            unit_kind=SourceUnitKind.SECTION,
            text=SourceUnitText("# FAQ\n\nBody"),
            heading_path=HeadingPath(("FAQ",)),
            lineage=SourceUnitLineage(),
            ordinal=0,
            created_at=_now(),
        )


@pytest.mark.asyncio
async def test_read_workspace_includes_raw_claim_and_source_unit_provenance() -> None:
    result = await ReadDraftClaimCurationWorkspace(
        curation_workspace_repository=FakeCurationRepository(),
        draft_claim_observation_read_repository=FakeDraftClaimRepository(),
        source_management_repository=FakeSourceRepository(),
    ).execute(workflow_run_id="workflow-1")

    assert result is not None
    payload = result.to_json_dict()
    assert payload["workspace"]["workspace_ref"] == "workspace-1"
    item = payload["items"][0]
    assert item["provenance"]["raw_claims"][0]["raw_claim_ref"] == "claim-a"
    assert item["provenance"]["source_units"][0]["source_unit_text"] == "# FAQ\n\nBody"
    assert item["audit"] == {}

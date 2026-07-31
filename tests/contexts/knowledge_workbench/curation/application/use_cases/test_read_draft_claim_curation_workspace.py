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


def _payload(claim_ref: str = "claim-a") -> dict[str, object]:
    return {
        "key": "refund_support",
        "claim": "Product supports refunds.",
        "claim_kind": "capability",
        "granularity": "atomic",
        "source_claim_refs": [claim_ref],
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


def _multi_item_snapshot() -> DraftClaimCurationWorkspaceSnapshot:
    items: list[DraftClaimCurationWorkspaceItem] = []
    for index in range(3):
        claim_ref = f"claim-{index}"
        payload = DraftClaimCurationItemEditablePayload.from_payload(_payload(claim_ref))
        items.append(
            DraftClaimCurationWorkspaceItem(
                item_ref=f"item-{index}",
                workspace_ref="workspace-1",
                workflow_run_id="workflow-1",
                group_ref=f"group-{index}",
                compacted_node_ref=f"compacted-{index}",
                source_claim_refs=(claim_ref,),
                original_payload=payload,
                editable_payload=payload,
                excluded=False,
                exclusion_reason=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )

    return DraftClaimCurationWorkspaceSnapshot(
        workspace=DraftClaimCurationWorkspace(
            workspace_ref="workspace-1",
            workflow_run_id="workflow-1",
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            status=DraftClaimCurationWorkspaceStatus.DRAFT,
            created_at=_now(),
            updated_at=_now(),
        ),
        items=tuple(items),
    )


@dataclass(slots=True)
class FakeCurationRepository:
    snapshot: DraftClaimCurationWorkspaceSnapshot | None = None

    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None:
        del workflow_run_id
        return self.snapshot or _snapshot()


@dataclass(slots=True)
class FakeDraftClaimRepository:
    calls: list[tuple[str, ...]] = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    async def list_by_observation_refs(
        self,
        *,
        observation_refs: tuple[str, ...],
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        self.calls.append(observation_refs)
        return tuple(
            DraftClaimObservationReadModel(
                observation_ref=observation_ref,
                source_unit_ref=f"source-unit-{index}",
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
                claim_index=index,
                created_at=_now(),
            )
            for index, observation_ref in enumerate(observation_refs)
        )


@dataclass(slots=True)
class FakeSourceRepository:
    load_calls: list[SourceUnitRef] = None
    list_calls: list[SourceDocumentRef] = None

    def __post_init__(self) -> None:
        if self.load_calls is None:
            self.load_calls = []
        if self.list_calls is None:
            self.list_calls = []

    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        self.load_calls.append(unit_ref)
        return _source_unit(unit_ref=unit_ref, ordinal=0)

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        self.list_calls.append(document_ref)
        return tuple(
            _source_unit(unit_ref=SourceUnitRef(f"source-unit-{index}"), ordinal=index)
            for index in range(3)
        )


def _source_unit(*, unit_ref: SourceUnitRef, ordinal: int) -> SourceUnit:
    return SourceUnit(
        unit_ref=unit_ref,
        document_ref=SourceDocumentRef("source-document:project-1:abc"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("# FAQ\n\nBody"),
        heading_path=HeadingPath(("FAQ",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
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


@pytest.mark.asyncio
async def test_read_workspace_batches_provenance_for_many_items() -> None:
    draft_claim_repository = FakeDraftClaimRepository()
    source_repository = FakeSourceRepository()

    result = await ReadDraftClaimCurationWorkspace(
        curation_workspace_repository=FakeCurationRepository(
            snapshot=_multi_item_snapshot()
        ),
        draft_claim_observation_read_repository=draft_claim_repository,
        source_management_repository=source_repository,
    ).execute(workflow_run_id="workflow-1")

    assert result is not None
    payload = result.to_json_dict()
    assert len(payload["items"]) == 3
    assert draft_claim_repository.calls == [("claim-0", "claim-1", "claim-2")]
    assert source_repository.list_calls == [
        SourceDocumentRef("source-document:project-1:abc")
    ]
    assert source_repository.load_calls == []

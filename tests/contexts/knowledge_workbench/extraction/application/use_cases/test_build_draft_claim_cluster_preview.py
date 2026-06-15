from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_cluster_preview import (
    DraftClaimClusterPreview,
    DraftClaimClusterPreviewBuildResult,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.build_draft_claim_cluster_preview import (
    BuildDraftClaimClusterPreview,
    DraftClaimClusterPreviewBuildError,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _node(
    *,
    group_ref: str = "group-1",
    key: str = "refund_support",
    claim: str = "Product supports refunds.",
) -> dict[str, object]:
    return {
        "group_ref": group_ref,
        "key": key,
        "claim": claim,
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
        "possible_questions": ["Q1", "Q2"],
        "exclusion_scope": "not X",
        "evidence_block": "E1",
    }


@dataclass(slots=True)
class FakeReductionRepository:
    nodes: tuple[object, ...] = field(default_factory=lambda: (_node(),))
    active_raw_count: int = 0

    async def count_active_raw_nodes(self, *, workflow_run_id: str) -> int:
        assert workflow_run_id == "workflow-1"
        return self.active_raw_count

    async def list_final_compacted_nodes_for_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[object, ...]:
        assert workflow_run_id == "workflow-1"
        return self.nodes


@dataclass(slots=True)
class FakePreviewRepository:
    previews: dict[str, DraftClaimClusterPreview] = field(default_factory=dict)

    async def save_preview(
        self,
        preview: DraftClaimClusterPreview,
    ) -> DraftClaimClusterPreviewBuildResult:
        created = preview.workflow_run_id not in self.previews
        self.previews[preview.workflow_run_id] = preview
        return DraftClaimClusterPreviewBuildResult(
            workflow_run_id=preview.workflow_run_id,
            claim_count=preview.claim_count,
            group_count=preview.group_count,
            created_preview=created,
            updated_preview=not created,
        )

    async def load_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimClusterPreview | None:
        return self.previews.get(workflow_run_id)


@pytest.mark.asyncio
async def test_builds_preview_from_active_compacted_nodes() -> None:
    preview_repository = FakePreviewRepository()

    result = await BuildDraftClaimClusterPreview(
        compaction_reduction_state_repository=FakeReductionRepository(
            nodes=(
                _node(group_ref="group-2", key="payments", claim="Payments exist."),
                _node(group_ref="group-1"),
            )
        ),
        cluster_preview_repository=preview_repository,
    ).execute(workflow_run_id="workflow-1", created_at=_now())

    assert result.claim_count == 2
    assert result.group_count == 2
    preview = await preview_repository.load_preview(workflow_run_id="workflow-1")
    assert preview is not None
    assert [group.group_ref for group in preview.groups] == ["group-1", "group-2"]
    assert preview.groups[0].claims[0].key == "refund_support"
    assert preview.groups[0].claims[0].possible_questions == ("Q1", "Q2")
    assert preview.groups[0].claims[0].exclusion_scope == "not X"
    assert preview.groups[0].claims[0].evidence_block == "E1"


@pytest.mark.asyncio
async def test_persists_preview_idempotently() -> None:
    preview_repository = FakePreviewRepository()
    use_case = BuildDraftClaimClusterPreview(
        compaction_reduction_state_repository=FakeReductionRepository(),
        cluster_preview_repository=preview_repository,
    )

    first = await use_case.execute(workflow_run_id="workflow-1", created_at=_now())
    second = await use_case.execute(workflow_run_id="workflow-1", created_at=_now())

    assert first.created_preview is True
    assert second.updated_preview is True
    assert len(preview_repository.previews) == 1


@pytest.mark.asyncio
async def test_rejects_if_active_raw_nodes_remain() -> None:
    with pytest.raises(DraftClaimClusterPreviewBuildError, match="active raw"):
        await BuildDraftClaimClusterPreview(
            compaction_reduction_state_repository=FakeReductionRepository(
                active_raw_count=1
            ),
            cluster_preview_repository=FakePreviewRepository(),
        ).execute(workflow_run_id="workflow-1", created_at=_now())


@pytest.mark.asyncio
async def test_rejects_if_no_compacted_nodes_exist() -> None:
    with pytest.raises(
        DraftClaimClusterPreviewBuildError, match="without active compacted"
    ):
        await BuildDraftClaimClusterPreview(
            compaction_reduction_state_repository=FakeReductionRepository(nodes=()),
            cluster_preview_repository=FakePreviewRepository(),
        ).execute(workflow_run_id="workflow-1", created_at=_now())

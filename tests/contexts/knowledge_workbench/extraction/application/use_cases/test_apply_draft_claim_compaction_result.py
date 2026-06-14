from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    DraftClaimCompactionApplyOutputKind,
    DraftClaimCompactionApplyResultCommand,
    compacted_claim_node_ref,
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionTriple,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNextWorkItem,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionPlannerDecision,
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionApplyPersistenceResult,
    DraftClaimCompactionReductionStatePersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.apply_draft_claim_compaction_result import (
    ApplyDraftClaimCompactionResult,
)


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeReductionStateRepository:
    applied: bool = False

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        assert workflow_run_id == "workflow-1"
        assert group_ref == "group-1"
        return DraftClaimCompactionPlannerState(cluster_ref="group-1", nodes=())

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes,
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        del workflow_run_id, group_ref, raw_nodes, created_at
        raise AssertionError("seed must not be called")

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compacted_claims: tuple[DraftClaimCompactionOutputClaim, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        assert workflow_run_id == "workflow-1"
        assert group_ref == "group-1"
        assert batch_ref == "batch-1"
        assert work_item_id == "work-item-1"
        assert round_index == 0
        assert created_at == _now()
        assert compacted_claims[0].source_claim_refs == ("claim-a", "claim-b")
        self.applied = True
        return _persistence_result()

    async def apply_reduced_rewrite_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        source_node_refs,
        rewrite,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del workflow_run_id, group_ref, batch_ref, work_item_id
        del round_index, source_node_refs, rewrite, created_at
        raise AssertionError("reduced rewrite must not be called")


@dataclass(frozen=True, slots=True)
class FakePlannerPolicy:
    def plan_next_step(
        self,
        state: DraftClaimCompactionPlannerState,
    ) -> DraftClaimCompactionPlannerDecision:
        assert state.cluster_ref == "group-1"
        return DraftClaimCompactionPlannerDecision(
            next_work_item=DraftClaimCompactionNextWorkItem(
                work_type=DraftClaimCompactionNextWorkItemType.DONE,
                node_refs=(),
            ),
            reason="done in fake",
        )


@pytest.mark.asyncio
async def test_apply_compacted_output_reloads_state_and_returns_next_decision() -> None:
    repository = FakeReductionStateRepository()
    command = DraftClaimCompactionApplyResultCommand(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        left_node_ref=raw_claim_node_ref(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            observation_ref="claim-a",
        ),
        right_node_ref=raw_claim_node_ref(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            observation_ref="claim-b",
        ),
        output_kind=DraftClaimCompactionApplyOutputKind.COMPACTED_CLAIMS,
        compacted_claims=(_compacted_claim(("claim-a", "claim-b")),),
        reduced_rewrite=None,
        created_at=_now(),
    )

    outcome = await ApplyDraftClaimCompactionResult(
        reduction_state_repository=repository,
        reduction_planner_policy=FakePlannerPolicy(),
    ).execute(command)

    assert repository.applied is True
    assert outcome.created_node_refs == (
        compacted_claim_node_ref(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            source_claim_refs=("claim-a", "claim-b"),
        ),
    )
    assert outcome.next_decision.work_type is DraftClaimCompactionNextWorkItemType.DONE


def _compacted_claim(
    source_refs: tuple[str, ...],
    *,
    key: str = "refund_support",
) -> DraftClaimCompactionOutputClaim:
    return DraftClaimCompactionOutputClaim(
        key=key,
        claim="Product supports refunds.",
        claim_kind="capability",
        granularity="atomic",
        source_claim_refs=source_refs,
        triples=(
            DraftClaimCompactionTriple(
                subject="Product",
                predicate="has_capability",
                object="refunds",
                qualifiers=(),
            ),
        ),
        merge_decision="merged" if len(source_refs) > 1 else "unmerged",
    )


def _persistence_result() -> DraftClaimCompactionApplyPersistenceResult:
    return DraftClaimCompactionApplyPersistenceResult(
        inserted_node_count=1,
        updated_node_count=2,
        inserted_source_count=2,
        inserted_comparison_count=1,
        superseded_node_count=2,
        already_exists_count=0,
    )

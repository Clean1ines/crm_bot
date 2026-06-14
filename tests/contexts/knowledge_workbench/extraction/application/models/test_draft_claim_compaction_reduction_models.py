from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID,
    PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID,
    DraftClaimCompactionBudgetFit,
    DraftClaimCompactionBudgetFitStatus,
    DraftClaimCompactionComparison,
    DraftClaimCompactionComparisonStatus,
    DraftClaimCompactionNextWorkItem,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionPlannerDecision,
    DraftClaimCompactionPlannerState,
)


def test_node_accepts_internal_raw_and_compacted_kinds() -> None:
    raw = DraftClaimCompactionNode(
        node_ref="raw-a",
        node_kind="raw",
        source_claim_refs=("claim-a",),
    )
    compacted = DraftClaimCompactionNode(
        node_ref="compacted-a",
        node_kind="compacted",
        source_claim_refs=("claim-a", "claim-b"),
    )

    assert raw.node_kind is DraftClaimCompactionNodeKind.RAW
    assert compacted.node_kind is DraftClaimCompactionNodeKind.COMPACTED


def test_node_rejects_empty_source_claim_refs() -> None:
    with pytest.raises(ValueError, match="source_claim_refs"):
        DraftClaimCompactionNode(
            node_ref="raw-a",
            node_kind=DraftClaimCompactionNodeKind.RAW,
            source_claim_refs=(),
        )


def test_comparison_pair_key_is_deterministic() -> None:
    comparison = DraftClaimCompactionComparison(
        left_node_ref="node-b",
        right_node_ref="node-a",
        status="not_merged",
    )

    assert comparison.status is DraftClaimCompactionComparisonStatus.NOT_MERGED
    assert comparison.pair_key == ("node-a", "node-b")


def test_planner_state_rejects_duplicate_node_refs() -> None:
    node = DraftClaimCompactionNode(
        node_ref="raw-a",
        node_kind=DraftClaimCompactionNodeKind.RAW,
        source_claim_refs=("claim-a",),
    )

    with pytest.raises(ValueError, match="node_ref"):
        DraftClaimCompactionPlannerState(
            cluster_ref="cluster-a",
            nodes=(node, node),
        )


def test_budget_fit_records_primary_and_degraded_models() -> None:
    fit = DraftClaimCompactionBudgetFit(
        status="too_large_even_reduced",
        estimated_input_tokens=120000,
    )

    assert fit.status is DraftClaimCompactionBudgetFitStatus.TOO_LARGE_EVEN_REDUCED
    assert fit.primary_model_id == PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID
    assert fit.degraded_candidate_model_id == DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID


def test_next_work_item_wait_boundary_can_carry_degraded_candidate() -> None:
    decision = DraftClaimCompactionPlannerDecision(
        next_work_item=DraftClaimCompactionNextWorkItem(
            work_type="wait_for_user_model_choice",
            node_refs=(),
            degraded_model_id=DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID,
        ),
        reason="needs user choice",
    )

    assert decision.work_type is (
        DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
    )
    assert decision.node_refs == ()
    assert (
        decision.next_work_item.degraded_model_id
        == DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID
    )

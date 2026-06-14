from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID,
    DraftClaimCompactionBudgetFit,
    DraftClaimCompactionBudgetFitStatus,
    DraftClaimCompactionComparison,
    DraftClaimCompactionComparisonStatus,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_reduction_planner_policy import (
    DraftClaimCompactionReductionPlannerPolicy,
)


def _raw(ref: str, *, active: bool = True) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=ref,
        node_kind=DraftClaimCompactionNodeKind.RAW,
        source_claim_refs=(f"source-{ref}",),
        active=active,
    )


def _compacted(ref: str, *, active: bool = True) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=ref,
        node_kind=DraftClaimCompactionNodeKind.COMPACTED,
        source_claim_refs=(f"source-{ref}",),
        active=active,
    )


def _comparison(
    left: str,
    right: str,
    status: DraftClaimCompactionComparisonStatus,
    *,
    result: str | None = None,
) -> DraftClaimCompactionComparison:
    return DraftClaimCompactionComparison(
        left_node_ref=left,
        right_node_ref=right,
        status=status,
        result_node_ref=result,
    )


def _state(
    *,
    nodes: tuple[DraftClaimCompactionNode, ...],
    comparisons: tuple[DraftClaimCompactionComparison, ...] = (),
    budget_fit: DraftClaimCompactionBudgetFit | None = None,
) -> DraftClaimCompactionPlannerState:
    return DraftClaimCompactionPlannerState(
        cluster_ref="cluster-a",
        nodes=nodes,
        comparisons=comparisons,
        budget_fit=budget_fit
        or DraftClaimCompactionBudgetFit(
            DraftClaimCompactionBudgetFitStatus.FITS_PRIMARY,
        ),
    )


def _plan(
    state: DraftClaimCompactionPlannerState,
):
    return DraftClaimCompactionReductionPlannerPolicy().plan_next_step(state)


def test_compacted_vs_compacted_has_priority_over_mixed_and_raw() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
                _raw("X"),
            ),
        )
    )

    assert (
        decision.work_type
        is DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    )
    assert decision.node_refs == ("A", "B")


def test_known_different_compacted_pair_blocks_raw_bridge_to_other_side() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
                _raw("X"),
            ),
            comparisons=(
                _comparison(
                    "A",
                    "B",
                    DraftClaimCompactionComparisonStatus.NOT_MERGED,
                ),
                _comparison(
                    "A",
                    "X",
                    DraftClaimCompactionComparisonStatus.MERGED,
                    result="A_with_X",
                ),
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE
    assert decision.node_refs != ("B", "X")


def test_too_large_compacted_pair_uses_pending_raw_as_bridge() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
                _raw("X"),
            ),
            comparisons=(
                _comparison(
                    "A",
                    "B",
                    DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL,
                ),
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.MIXED
    assert decision.node_refs == ("A", "X")


def test_bridge_when_both_sides_merge_plans_reduced_rewrite() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
                _raw("X"),
            ),
            comparisons=(
                _comparison(
                    "A",
                    "B",
                    DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL,
                ),
                _comparison(
                    "A",
                    "X",
                    DraftClaimCompactionComparisonStatus.MERGED,
                    result="A_with_X",
                ),
                _comparison(
                    "B",
                    "X",
                    DraftClaimCompactionComparisonStatus.MERGED,
                    result="B_with_X",
                ),
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE
    assert decision.node_refs == ("A_with_X", "B_with_X")


def test_only_one_bridge_side_merged_does_not_plan_reduced_rewrite() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
                _raw("X"),
            ),
            comparisons=(
                _comparison(
                    "A",
                    "B",
                    DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL,
                ),
                _comparison(
                    "A",
                    "X",
                    DraftClaimCompactionComparisonStatus.MERGED,
                    result="A_with_X",
                ),
                _comparison(
                    "B",
                    "X",
                    DraftClaimCompactionComparisonStatus.NOT_MERGED,
                ),
            ),
        )
    )

    assert (
        decision.work_type is not DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE
    )


def test_merged_compacted_result_is_compared_with_pending_raw() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A", active=False),
                _compacted("B", active=False),
                _compacted("C"),
                _raw("X"),
            ),
            comparisons=(
                _comparison(
                    "A",
                    "B",
                    DraftClaimCompactionComparisonStatus.MERGED,
                    result="C",
                ),
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.MIXED
    assert decision.node_refs == ("C", "X")


def test_user_choice_boundary_when_reduced_payload_is_too_large() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
            ),
            budget_fit=DraftClaimCompactionBudgetFit(
                status=DraftClaimCompactionBudgetFitStatus.TOO_LARGE_EVEN_REDUCED,
                estimated_input_tokens=150000,
            ),
        )
    )

    assert decision.work_type is (
        DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
    )
    assert decision.node_refs == ()
    assert (
        decision.next_work_item.degraded_model_id
        == DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID
    )


def test_done_when_active_nodes_are_pairwise_known_different() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A"),
                _compacted("B"),
            ),
            comparisons=(
                _comparison(
                    "A",
                    "B",
                    DraftClaimCompactionComparisonStatus.NOT_MERGED,
                ),
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE
    assert decision.node_refs == ()


def test_done_when_only_single_active_node_remains() -> None:
    decision = _plan(_state(nodes=(_compacted("A"),)))

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE
    assert decision.node_refs == ()

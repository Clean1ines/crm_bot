from __future__ import annotations

from itertools import combinations

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


def _raw(
    ref: str,
    *,
    active: bool = True,
    estimated_input_tokens: int = 1,
) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=ref,
        node_kind=DraftClaimCompactionNodeKind.RAW,
        source_claim_refs=(f"source-{ref}",),
        active=active,
        estimated_input_tokens=estimated_input_tokens,
    )


def _compacted(
    ref: str,
    *,
    active: bool = True,
    estimated_input_tokens: int = 1,
    source_claim_refs: tuple[str, ...] | None = None,
) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=ref,
        node_kind=DraftClaimCompactionNodeKind.COMPACTED,
        source_claim_refs=source_claim_refs or (f"source-{ref}",),
        active=active,
        estimated_input_tokens=estimated_input_tokens,
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


def test_next_work_item_carries_prompt_estimate_from_node_refs() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A", estimated_input_tokens=1200),
                _compacted("B", estimated_input_tokens=1400),
                _raw("X", estimated_input_tokens=999),
            ),
        )
    )

    assert (
        decision.work_type
        is DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    )
    assert decision.node_refs == ("A", "B")
    assert decision.next_work_item.prompt_tokens == 2150
    assert decision.next_work_item.artifact_tokens == 2600
    assert decision.next_work_item.input_tokens == 4750
    assert decision.next_work_item.prompt_tokens == 2150
    assert decision.next_work_item.artifact_tokens == 2600
    assert decision.next_work_item.input_tokens == 4750
    assert decision.next_work_item.estimated_prompt_tokens == 4750
    assert decision.next_work_item.estimated_completion_tokens == 2600


def test_compacted_pair_uses_enriched_prompt_for_tpm_boundary() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A", estimated_input_tokens=1475),
                _compacted("B", estimated_input_tokens=1475),
            ),
        )
    )

    assert decision.work_type is (
        DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
    )
    assert decision.node_refs == ("A", "B")
    assert decision.next_work_item.prompt_tokens == 2150
    assert decision.next_work_item.artifact_tokens == 2950
    assert decision.next_work_item.input_tokens == 5100
    assert decision.next_work_item.prompt_tokens == 2150
    assert decision.next_work_item.artifact_tokens == 2950
    assert decision.next_work_item.input_tokens == 5100
    assert decision.next_work_item.estimated_prompt_tokens == 5100
    assert decision.next_work_item.estimated_completion_tokens == 2950


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


def test_estimated_tpm_overflow_uses_pending_raw_as_bridge_before_dispatch() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A", estimated_input_tokens=1600),
                _compacted("B", estimated_input_tokens=1600),
                _raw("X", estimated_input_tokens=100),
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.MIXED
    assert decision.node_refs == ("A", "X")


def test_estimated_tpm_overflow_without_bridge_waits_for_user_choice() -> None:
    decision = _plan(
        _state(
            nodes=(
                _compacted("A", estimated_input_tokens=1600),
                _compacted("B", estimated_input_tokens=1600),
            ),
        )
    )

    assert decision.work_type is (
        DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
    )
    assert decision.node_refs == ("A", "B")
    assert decision.next_work_item.user_choice_resume_work_type is (
        DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    )


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
    assert decision.node_refs == ("A", "B")
    assert decision.next_work_item.user_choice_resume_work_type is (
        DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    )
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


def test_done_for_five_pairwise_known_different_outputs() -> None:
    node_refs = ("1-prime", "2-prime", "3-prime", "4-prime", "5")
    decision = _plan(
        _state(
            nodes=tuple(_compacted(node_ref) for node_ref in node_refs),
            comparisons=tuple(
                _comparison(
                    left,
                    right,
                    DraftClaimCompactionComparisonStatus.NOT_MERGED,
                )
                for left, right in combinations(node_refs, 2)
            ),
        )
    )

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE
    assert decision.node_refs == ()


def test_done_when_only_single_active_node_remains() -> None:
    decision = _plan(_state(nodes=(_compacted("A"),)))

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE
    assert decision.node_refs == ()


def test_after_two_applied_compactions_compacted_vs_compacted_has_priority() -> None:
    decision = _plan(
        _state(
            nodes=(
                _raw("raw-5"),
                _compacted("A"),
                _compacted("B"),
            ),
        )
    )

    assert (
        decision.work_type
        is DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    )
    assert decision.node_refs == ("A", "B")


def test_planner_skips_pair_when_lineage_inherits_not_merge_edge() -> None:
    state = DraftClaimCompactionPlannerState(
        cluster_ref="group-1",
        nodes=(
            _compacted(
                "node-a",
                active=False,
                source_claim_refs=("claim-a",),
            ),
            _compacted(
                "node-c",
                source_claim_refs=("claim-c",),
            ),
            _compacted(
                "node-a5",
                source_claim_refs=("claim-a", "claim-5"),
            ),
        ),
        comparisons=(
            _comparison(
                "node-a",
                "node-c",
                DraftClaimCompactionComparisonStatus.NOT_MERGED,
            ),
        ),
    )

    decision = DraftClaimCompactionReductionPlannerPolicy().plan_next_step(state)

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE

from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
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


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionReductionPlannerPolicy:
    def plan_next_step(
        self,
        state: DraftClaimCompactionPlannerState,
    ) -> DraftClaimCompactionPlannerDecision:
        if state.budget_fit.status is (
            DraftClaimCompactionBudgetFitStatus.TOO_LARGE_EVEN_REDUCED
        ):
            return _wait_for_user_model_choice(
                state,
                "ordinary comparison and reduced rewrite exceed primary budget",
            )

        index = _ComparisonIndex(state.comparisons)
        active_nodes = _ordered_active_nodes(state)
        active_compacted = _nodes_by_kind(
            active_nodes,
            DraftClaimCompactionNodeKind.COMPACTED,
        )
        active_raw = _nodes_by_kind(active_nodes, DraftClaimCompactionNodeKind.RAW)

        reduced_rewrite = _find_bridge_rewrite(
            active_compacted=active_compacted,
            active_raw=active_raw,
            index=index,
        )
        if reduced_rewrite is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
                node_refs=reduced_rewrite,
                reason="two bridge comparisons merged after primary too-large pair",
            )

        compacted_pair = _first_uncompared_pair(active_compacted, index)
        if compacted_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
                node_refs=compacted_pair,
                reason="compacted-vs-compacted has highest priority",
            )

        bridge_pair = _find_bridge_comparison(
            active_compacted=active_compacted,
            active_raw=active_raw,
            index=index,
        )
        if bridge_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.MIXED,
                node_refs=bridge_pair,
                reason="primary too-large compacted pair can be probed through raw node",
            )

        mixed_pair = _first_uncompared_mixed_pair(
            active_compacted=active_compacted,
            active_raw=active_raw,
            index=index,
        )
        if mixed_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.MIXED,
                node_refs=mixed_pair,
                reason="pending raw node must be compared with compacted node",
            )

        raw_pair = _first_uncompared_pair(active_raw, index)
        if raw_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT,
                node_refs=raw_pair,
                reason="raw-vs-raw is lowest ordinary comparison priority",
            )

        if _has_unresolved_primary_too_large_pair(active_nodes, index):
            return _wait_for_user_model_choice(
                state,
                "unresolved comparison is too large for primary model",
            )

        return _decision(
            state=state,
            work_type=DraftClaimCompactionNextWorkItemType.DONE,
            node_refs=(),
            reason="all active nodes are reduced or pairwise known different",
        )


@dataclass(frozen=True, slots=True)
class _ComparisonIndex:
    comparisons: tuple[DraftClaimCompactionComparison, ...]

    def status(
        self,
        left_node_ref: str,
        right_node_ref: str,
    ) -> DraftClaimCompactionComparisonStatus | None:
        comparison = self._latest(left_node_ref, right_node_ref)
        if comparison is None:
            return None
        return comparison.status

    def result_node_ref(
        self,
        left_node_ref: str,
        right_node_ref: str,
    ) -> str | None:
        comparison = self._latest(left_node_ref, right_node_ref)
        if comparison is None:
            return None
        return comparison.result_node_ref

    def _latest(
        self,
        left_node_ref: str,
        right_node_ref: str,
    ) -> DraftClaimCompactionComparison | None:
        pair = _pair_key(left_node_ref, right_node_ref)
        for comparison in reversed(self.comparisons):
            if comparison.pair_key == pair:
                return comparison
        return None


def _ordered_active_nodes(
    state: DraftClaimCompactionPlannerState,
) -> tuple[DraftClaimCompactionNode, ...]:
    return tuple(sorted(state.active_nodes(), key=lambda node: node.node_ref))


def _nodes_by_kind(
    nodes: tuple[DraftClaimCompactionNode, ...],
    kind: DraftClaimCompactionNodeKind,
) -> tuple[DraftClaimCompactionNode, ...]:
    return tuple(node for node in nodes if node.node_kind is kind)


def _find_bridge_rewrite(
    *,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    active_raw: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> tuple[str, str] | None:
    for left, right in _node_pairs(active_compacted):
        if index.status(left.node_ref, right.node_ref) is not (
            DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL
        ):
            continue
        for raw in active_raw:
            left_status = index.status(left.node_ref, raw.node_ref)
            right_status = index.status(right.node_ref, raw.node_ref)
            if left_status is not DraftClaimCompactionComparisonStatus.MERGED:
                continue
            if right_status is not DraftClaimCompactionComparisonStatus.MERGED:
                continue
            left_result = index.result_node_ref(left.node_ref, raw.node_ref)
            right_result = index.result_node_ref(right.node_ref, raw.node_ref)
            if left_result is None or right_result is None:
                continue
            return _pair_key(left_result, right_result)
    return None


def _find_bridge_comparison(
    *,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    active_raw: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> tuple[str, str] | None:
    for left, right in _node_pairs(active_compacted):
        if index.status(left.node_ref, right.node_ref) is not (
            DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL
        ):
            continue
        for raw in active_raw:
            left_pair = _mixed_candidate(left, raw, active_compacted, index)
            if left_pair is not None:
                return left_pair
            right_pair = _mixed_candidate(right, raw, active_compacted, index)
            if right_pair is not None:
                return right_pair
    return None


def _first_uncompared_mixed_pair(
    *,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    active_raw: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> tuple[str, str] | None:
    for compacted in active_compacted:
        for raw in active_raw:
            pair = _mixed_candidate(compacted, raw, active_compacted, index)
            if pair is not None:
                return pair
    return None


def _mixed_candidate(
    compacted: DraftClaimCompactionNode,
    raw: DraftClaimCompactionNode,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> tuple[str, str] | None:
    if index.status(compacted.node_ref, raw.node_ref) is not None:
        return None
    if _blocked_by_known_different_compacted_node(
        compacted=compacted,
        raw=raw,
        active_compacted=active_compacted,
        index=index,
    ):
        return None
    return compacted.node_ref, raw.node_ref


def _blocked_by_known_different_compacted_node(
    *,
    compacted: DraftClaimCompactionNode,
    raw: DraftClaimCompactionNode,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> bool:
    for other in active_compacted:
        if other.node_ref == compacted.node_ref:
            continue
        raw_merged_with_other = (
            index.status(other.node_ref, raw.node_ref)
            is DraftClaimCompactionComparisonStatus.MERGED
        )
        compacted_known_different = (
            index.status(other.node_ref, compacted.node_ref)
            is DraftClaimCompactionComparisonStatus.NOT_MERGED
        )
        if raw_merged_with_other and compacted_known_different:
            return True
    return False


def _first_uncompared_pair(
    nodes: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> tuple[str, str] | None:
    for left, right in _node_pairs(nodes):
        if index.status(left.node_ref, right.node_ref) is None:
            return left.node_ref, right.node_ref
    return None


def _has_unresolved_primary_too_large_pair(
    active_nodes: tuple[DraftClaimCompactionNode, ...],
    index: _ComparisonIndex,
) -> bool:
    for left, right in _node_pairs(active_nodes):
        if index.status(left.node_ref, right.node_ref) is (
            DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL
        ):
            return True
    return False


def _node_pairs(
    nodes: tuple[DraftClaimCompactionNode, ...],
) -> tuple[tuple[DraftClaimCompactionNode, DraftClaimCompactionNode], ...]:
    pairs: list[tuple[DraftClaimCompactionNode, DraftClaimCompactionNode]] = []
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            pairs.append((left, right))
    return tuple(pairs)


def _pair_key(left_node_ref: str, right_node_ref: str) -> tuple[str, str]:
    left, right = sorted((left_node_ref, right_node_ref))
    return left, right


def _decision(
    *,
    state: DraftClaimCompactionPlannerState,
    work_type: DraftClaimCompactionNextWorkItemType,
    node_refs: tuple[str, ...],
    reason: str,
) -> DraftClaimCompactionPlannerDecision:
    return DraftClaimCompactionPlannerDecision(
        next_work_item=DraftClaimCompactionNextWorkItem(
            work_type=work_type,
            node_refs=node_refs,
            primary_model_id=state.primary_model_id,
            estimated_prompt_tokens=_estimated_prompt_tokens(
                state=state,
                node_refs=node_refs,
            ),
        ),
        reason=reason,
    )


def _estimated_prompt_tokens(
    *,
    state: DraftClaimCompactionPlannerState,
    node_refs: tuple[str, ...],
) -> int:
    nodes_by_ref = {node.node_ref: node for node in state.nodes}
    total = 0
    for node_ref in node_refs:
        node = nodes_by_ref.get(node_ref)
        if node is None:
            continue
        total += node.estimated_input_tokens

    if node_refs and total <= 0:
        return 1
    return total


def _wait_for_user_model_choice(
    state: DraftClaimCompactionPlannerState,
    reason: str,
) -> DraftClaimCompactionPlannerDecision:
    return DraftClaimCompactionPlannerDecision(
        next_work_item=DraftClaimCompactionNextWorkItem(
            work_type=DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE,
            node_refs=(),
            primary_model_id=state.primary_model_id,
            degraded_model_id=state.degraded_candidate_model_id,
        ),
        reason=reason,
    )

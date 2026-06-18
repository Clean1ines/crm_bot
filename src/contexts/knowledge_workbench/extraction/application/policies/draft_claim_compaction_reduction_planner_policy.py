from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionBudgetFitStatus,
    DraftClaimCompactionComparison,
    DraftClaimCompactionComparisonStatus,
    DraftClaimCompactionComponent,
    DraftClaimCompactionComponentIncompatibility,
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

        comparison_index = _ComparisonIndex(state.comparisons)
        component_index = _ComponentIndex.from_state(state)
        active_nodes = _ordered_active_nodes(state)
        active_compacted = _nodes_by_kind(
            active_nodes,
            DraftClaimCompactionNodeKind.COMPACTED,
        )
        active_raw = _nodes_by_kind(active_nodes, DraftClaimCompactionNodeKind.RAW)

        reduced_rewrite = _find_bridge_rewrite(
            active_compacted=active_compacted,
            active_raw=active_raw,
            comparison_index=comparison_index,
            component_index=component_index,
        )
        if reduced_rewrite is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
                node_refs=reduced_rewrite,
                reason="two bridge comparisons merged after primary too-large pair",
            )

        compacted_pair = _first_comparable_pair(
            active_compacted,
            comparison_index=comparison_index,
            component_index=component_index,
        )
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
            comparison_index=comparison_index,
            component_index=component_index,
        )
        if bridge_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.MIXED,
                node_refs=bridge_pair,
                reason="primary too-large compacted pair can be probed through raw node",
            )

        mixed_pair = _first_comparable_mixed_pair(
            active_compacted=active_compacted,
            active_raw=active_raw,
            comparison_index=comparison_index,
            component_index=component_index,
        )
        if mixed_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.MIXED,
                node_refs=mixed_pair,
                reason="pending raw node must be compared with compacted node",
            )

        raw_pair = _first_comparable_pair(
            active_raw,
            comparison_index=comparison_index,
            component_index=component_index,
        )
        if raw_pair is not None:
            return _decision(
                state=state,
                work_type=DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT,
                node_refs=raw_pair,
                reason="raw-vs-raw is lowest ordinary comparison priority",
            )

        if _has_unresolved_primary_too_large_pair(active_nodes, comparison_index):
            return _wait_for_user_model_choice(
                state,
                "unresolved comparison is too large for primary model",
            )

        return _decision(
            state=state,
            work_type=DraftClaimCompactionNextWorkItemType.DONE,
            node_refs=(),
            reason="all active components are reduced or known incompatible",
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


@dataclass(frozen=True, slots=True)
class _ComponentIndex:
    component_by_node_ref: dict[str, str]
    incompatible_pairs: frozenset[tuple[str, str]]

    @classmethod
    def from_state(cls, state: DraftClaimCompactionPlannerState) -> _ComponentIndex:
        if state.components:
            return cls._from_persisted_state(state)
        return cls._from_legacy_state(state)

    @classmethod
    def _from_persisted_state(
        cls,
        state: DraftClaimCompactionPlannerState,
    ) -> _ComponentIndex:
        component_by_node_ref: dict[str, str] = {}
        for component in state.components:
            if not component.active:
                continue
            component_by_node_ref[component.representative_node_ref] = (
                component.component_ref
            )

        incompatible_pairs = frozenset(
            incompatibility.pair_key
            for incompatibility in state.incompatibilities
            if incompatibility.left_component_ref in set(component_by_node_ref.values())
            and incompatibility.right_component_ref in set(component_by_node_ref.values())
        )
        return cls(
            component_by_node_ref=component_by_node_ref,
            incompatible_pairs=incompatible_pairs,
        )

    @classmethod
    def _from_legacy_state(
        cls,
        state: DraftClaimCompactionPlannerState,
    ) -> _ComponentIndex:
        active_nodes = state.active_nodes()
        active_refs = {node.node_ref for node in active_nodes}
        parents = {node_ref: node_ref for node_ref in active_refs}

        def find(node_ref: str) -> str:
            parent = parents[node_ref]
            if parent != node_ref:
                parents[node_ref] = find(parent)
            return parents[node_ref]

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root == right_root:
                return
            new_root = min(left_root, right_root)
            old_root = max(left_root, right_root)
            parents[old_root] = new_root

        for comparison in state.comparisons:
            if comparison.status is not DraftClaimCompactionComparisonStatus.MERGED:
                continue
            if (
                comparison.left_node_ref not in active_refs
                or comparison.right_node_ref not in active_refs
            ):
                continue
            union(comparison.left_node_ref, comparison.right_node_ref)

        component_by_node_ref = {
            node_ref: find(node_ref) for node_ref in sorted(active_refs)
        }

        incompatible_pairs: set[tuple[str, str]] = set()
        for comparison in state.comparisons:
            if comparison.status is not DraftClaimCompactionComparisonStatus.NOT_MERGED:
                continue
            if (
                comparison.left_node_ref not in active_refs
                or comparison.right_node_ref not in active_refs
            ):
                continue
            left_component = find(comparison.left_node_ref)
            right_component = find(comparison.right_node_ref)
            if left_component == right_component:
                continue
            incompatible_pairs.add(_pair_key(left_component, right_component))

        return cls(
            component_by_node_ref=component_by_node_ref,
            incompatible_pairs=frozenset(incompatible_pairs),
        )

    def can_compare(
        self,
        left_node_ref: str,
        right_node_ref: str,
        comparison_index: _ComparisonIndex,
    ) -> bool:
        left_component_ref = self.component_by_node_ref.get(left_node_ref, left_node_ref)
        right_component_ref = self.component_by_node_ref.get(
            right_node_ref,
            right_node_ref,
        )
        if left_component_ref == right_component_ref:
            return False
        if _pair_key(left_component_ref, right_component_ref) in self.incompatible_pairs:
            return False
        status = comparison_index.status(left_node_ref, right_node_ref)
        if status is DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL:
            return False
        return status is None


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
    comparison_index: _ComparisonIndex,
    component_index: _ComponentIndex,
) -> tuple[str, str] | None:
    for left, right in _node_pairs(active_compacted):
        if comparison_index.status(left.node_ref, right.node_ref) is not (
            DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL
        ):
            continue
        for raw in active_raw:
            left_status = comparison_index.status(left.node_ref, raw.node_ref)
            right_status = comparison_index.status(right.node_ref, raw.node_ref)
            if left_status is not DraftClaimCompactionComparisonStatus.MERGED:
                continue
            if right_status is not DraftClaimCompactionComparisonStatus.MERGED:
                continue
            left_result = comparison_index.result_node_ref(left.node_ref, raw.node_ref)
            right_result = comparison_index.result_node_ref(right.node_ref, raw.node_ref)
            if left_result is None or right_result is None:
                continue
            if not component_index.can_compare(
                left_result,
                right_result,
                comparison_index,
            ):
                continue
            return _pair_key(left_result, right_result)
    return None


def _find_bridge_comparison(
    *,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    active_raw: tuple[DraftClaimCompactionNode, ...],
    comparison_index: _ComparisonIndex,
    component_index: _ComponentIndex,
) -> tuple[str, str] | None:
    for left, right in _node_pairs(active_compacted):
        if comparison_index.status(left.node_ref, right.node_ref) is not (
            DraftClaimCompactionComparisonStatus.TOO_LARGE_FOR_PRIMARY_MODEL
        ):
            continue
        for raw in active_raw:
            left_pair = _mixed_candidate(
                left,
                raw,
                comparison_index=comparison_index,
                component_index=component_index,
            )
            if left_pair is not None:
                return left_pair
            right_pair = _mixed_candidate(
                right,
                raw,
                comparison_index=comparison_index,
                component_index=component_index,
            )
            if right_pair is not None:
                return right_pair
    return None


def _first_comparable_mixed_pair(
    *,
    active_compacted: tuple[DraftClaimCompactionNode, ...],
    active_raw: tuple[DraftClaimCompactionNode, ...],
    comparison_index: _ComparisonIndex,
    component_index: _ComponentIndex,
) -> tuple[str, str] | None:
    for compacted in active_compacted:
        for raw in active_raw:
            pair = _mixed_candidate(
                compacted,
                raw,
                comparison_index=comparison_index,
                component_index=component_index,
            )
            if pair is not None:
                return pair
    return None


def _mixed_candidate(
    compacted: DraftClaimCompactionNode,
    raw: DraftClaimCompactionNode,
    *,
    comparison_index: _ComparisonIndex,
    component_index: _ComponentIndex,
) -> tuple[str, str] | None:
    if not component_index.can_compare(
        compacted.node_ref,
        raw.node_ref,
        comparison_index,
    ):
        return None
    return compacted.node_ref, raw.node_ref


def _first_comparable_pair(
    nodes: tuple[DraftClaimCompactionNode, ...],
    *,
    comparison_index: _ComparisonIndex,
    component_index: _ComponentIndex,
) -> tuple[str, str] | None:
    for left, right in _node_pairs(nodes):
        if component_index.can_compare(left.node_ref, right.node_ref, comparison_index):
            return left.node_ref, right.node_ref
    return None


def _has_unresolved_primary_too_large_pair(
    active_nodes: tuple[DraftClaimCompactionNode, ...],
    comparison_index: _ComparisonIndex,
) -> bool:
    for left, right in _node_pairs(active_nodes):
        if comparison_index.status(left.node_ref, right.node_ref) is (
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

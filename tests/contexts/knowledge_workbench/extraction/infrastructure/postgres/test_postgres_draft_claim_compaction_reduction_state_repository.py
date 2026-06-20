from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionTriple,
    DraftClaimReducedRewriteOutput,
)
from src.contexts.knowledge_workbench.extraction.application.models.enriched_draft_claim_compaction_output import (
    EnrichedDraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionComparisonStatus,
    DraftClaimCompactionNodeKind,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_reduction_state_repository import (
    PostgresDraftClaimCompactionReductionStateRepository,
    build_initial_raw_node,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    compacted_claim_node_ref,
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNextWorkItemType,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_reduction_planner_policy import (
    DraftClaimCompactionReductionPlannerPolicy,
)


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeReductionStateConnection:
    nodes: dict[str, dict[str, object]] = field(default_factory=dict)
    sources: dict[tuple[str, str], dict[str, object]] = field(default_factory=dict)
    comparisons: dict[tuple[str, str, int], dict[str, object]] = field(
        default_factory=dict
    )
    components: dict[str, dict[str, object]] = field(default_factory=dict)
    incompatibilities: dict[tuple[str, str], dict[str, object]] = field(
        default_factory=dict
    )

    async def execute(self, query: str, *args: object) -> object:
        if "INSERT INTO draft_claim_compaction_components" in query:
            component_ref = _str_arg(args[0])
            self.components[component_ref] = {
                "component_ref": component_ref,
                "workflow_run_id": _str_arg(args[1]),
                "group_ref": _str_arg(args[2]),
                "representative_node_ref": _str_arg(args[3]),
                "active": _bool_arg(args[4]),
                "source_claim_refs": json.loads(_str_arg(args[5])),
                "supersedes_component_refs": json.loads(_str_arg(args[6])),
            }
            return "INSERT 0 1"

        if "UPDATE draft_claim_compaction_components" in query:
            component_refs = tuple(str(item) for item in _sequence_arg(args[3]))
            updated = 0
            for component_ref in component_refs:
                component = self.components.get(component_ref)
                if component is not None and component["active"] is True:
                    component["active"] = False
                    updated += 1
            return f"UPDATE {updated}"

        if "INSERT INTO draft_claim_compaction_component_incompatibilities" in query:
            key = (_str_arg(args[3]), _str_arg(args[4]))
            if key in self.incompatibilities:
                return "INSERT 0 0"
            self.incompatibilities[key] = {
                "incompatibility_ref": _str_arg(args[0]),
                "workflow_run_id": _str_arg(args[1]),
                "group_ref": _str_arg(args[2]),
                "left_component_ref": key[0],
                "right_component_ref": key[1],
                "source_comparison_ref": _optional_str_arg(args[5]),
            }
            return "INSERT 0 1"

        if "INSERT INTO draft_claim_compaction_nodes" in query:
            node_ref = _str_arg(args[0])
            if node_ref in self.nodes:
                return "INSERT 0 0"
            is_enriched_compacted_insert = len(args) >= 17
            self.nodes[node_ref] = {
                "node_ref": node_ref,
                "workflow_run_id": _str_arg(args[1]),
                "group_ref": _str_arg(args[2]),
                "node_kind": _str_arg(args[3]),
                "active": _bool_arg(args[4]),
                "source_claim_refs": json.loads(_str_arg(args[5])),
                "supersedes_node_refs": json.loads(_str_arg(args[6])),
                "estimated_input_tokens": _int_arg(args[7]),
                "compacted_key": _optional_str_arg(args[8])
                if is_enriched_compacted_insert
                else None,
                "compacted_claim": _optional_str_arg(args[9])
                if is_enriched_compacted_insert
                else None,
                "compacted_claim_kind": _optional_str_arg(args[10])
                if is_enriched_compacted_insert
                else None,
                "compacted_granularity": _optional_str_arg(args[11])
                if is_enriched_compacted_insert
                else None,
                "compacted_merge_decision": _optional_str_arg(args[12])
                if is_enriched_compacted_insert
                else None,
                "compacted_triples": (
                    json.loads(_str_arg(args[13]))
                    if is_enriched_compacted_insert
                    else []
                ),
                "compacted_payload": (
                    json.loads(_str_arg(args[14]))
                    if is_enriched_compacted_insert
                    else None
                ),
            }
            return "INSERT 0 1"

        if "UPDATE draft_claim_compaction_nodes" in query:
            node_refs = tuple(str(item) for item in _sequence_arg(args[1]))
            updated = 0
            for node_ref in node_refs:
                node = self.nodes.get(node_ref)
                if node is not None and node["active"] is True:
                    node["active"] = False
                    updated += 1
            return f"UPDATE {updated}"

        if "INSERT INTO draft_claim_compaction_comparisons" in query:
            key = (_str_arg(args[3]), _str_arg(args[4]), _int_arg(args[7]))
            if key in self.comparisons:
                return "INSERT 0 0"
            self.comparisons[key] = {
                "comparison_ref": _str_arg(args[0]),
                "workflow_run_id": _str_arg(args[1]),
                "group_ref": _str_arg(args[2]),
                "left_node_ref": key[0],
                "right_node_ref": key[1],
                "status": _str_arg(args[5]),
                "result_node_ref": _optional_str_arg(args[6]),
                "round_index": key[2],
            }
            return "INSERT 0 1"

        if "INSERT INTO draft_claim_compaction_node_sources" in query:
            key = (_str_arg(args[0]), _str_arg(args[1]))
            if key in self.sources:
                return "INSERT 0 0"
            self.sources[key] = {
                "node_ref": key[0],
                "source_ref": key[1],
                "source_kind": _str_arg(args[2]),
            }
            return "INSERT 0 1"

        raise AssertionError(f"unexpected execute query: {query}")

    async def fetchval(self, query: str, *args: object) -> object | None:
        if "FROM draft_claim_compaction_components" in query:
            workflow_run_id = _str_arg(args[0])
            group_ref = _str_arg(args[1])
            node_ref = _str_arg(args[2])
            for component in sorted(
                self.components.values(),
                key=lambda row: str(row["component_ref"]),
            ):
                if (
                    component["workflow_run_id"] == workflow_run_id
                    and component["group_ref"] == group_ref
                    and component["representative_node_ref"] == node_ref
                    and component["active"] is True
                ):
                    return component["component_ref"]
            return None
        raise AssertionError(f"unexpected fetchval query: {query}")

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        if (
            "COUNT(*) FILTER" in query
            and "FROM draft_claim_compaction_components" in query
        ):
            workflow_run_id = _str_arg(args[0])
            group_refs = sorted(
                {
                    str(component["group_ref"])
                    for component in self.components.values()
                    if component["workflow_run_id"] == workflow_run_id
                }
            )
            return [
                {
                    "group_ref": group_ref,
                    "active_component_count": sum(
                        1
                        for component in self.components.values()
                        if component["workflow_run_id"] == workflow_run_id
                        and component["group_ref"] == group_ref
                        and component["active"] is True
                    ),
                }
                for group_ref in group_refs
            ]

        if "FROM draft_claim_compaction_components" in query:
            workflow_run_id = _str_arg(args[0])
            group_ref = _str_arg(args[1])
            return [
                component
                for component in sorted(
                    self.components.values(),
                    key=lambda row: str(row["component_ref"]),
                )
                if component["workflow_run_id"] == workflow_run_id
                and component["group_ref"] == group_ref
            ]

        if (
            "COUNT(*) AS component_incompatibility_count" in query
            and "FROM draft_claim_compaction_component_incompatibilities" in query
        ):
            workflow_run_id = _str_arg(args[0])
            group_refs = sorted(
                {
                    str(incompatibility["group_ref"])
                    for incompatibility in self.incompatibilities.values()
                    if incompatibility["workflow_run_id"] == workflow_run_id
                }
            )
            return [
                {
                    "group_ref": group_ref,
                    "component_incompatibility_count": sum(
                        1
                        for incompatibility in self.incompatibilities.values()
                        if incompatibility["workflow_run_id"] == workflow_run_id
                        and incompatibility["group_ref"] == group_ref
                    ),
                }
                for group_ref in group_refs
            ]

        if "FROM draft_claim_compaction_component_incompatibilities" in query:
            workflow_run_id = _str_arg(args[0])
            group_ref = _str_arg(args[1])
            if len(args) >= 3:
                component_refs = set(str(item) for item in _sequence_arg(args[2]))
                return [
                    incompatibility
                    for incompatibility in sorted(
                        self.incompatibilities.values(),
                        key=lambda row: (
                            str(row["left_component_ref"]),
                            str(row["right_component_ref"]),
                        ),
                    )
                    if incompatibility["workflow_run_id"] == workflow_run_id
                    and incompatibility["group_ref"] == group_ref
                    and (
                        incompatibility["left_component_ref"] in component_refs
                        or incompatibility["right_component_ref"] in component_refs
                    )
                ]
            return [
                incompatibility
                for incompatibility in sorted(
                    self.incompatibilities.values(),
                    key=lambda row: (
                        str(row["left_component_ref"]),
                        str(row["right_component_ref"]),
                    ),
                )
                if incompatibility["workflow_run_id"] == workflow_run_id
                and incompatibility["group_ref"] == group_ref
            ]

        if "COUNT(*) FILTER" in query and "FROM draft_claim_compaction_nodes" in query:
            workflow_run_id = _str_arg(args[0])
            rows: list[Mapping[str, object]] = []
            group_refs = sorted(
                {
                    str(node["group_ref"])
                    for node in self.nodes.values()
                    if node["workflow_run_id"] == workflow_run_id
                }
            )
            for group_ref in group_refs:
                nodes = [
                    node
                    for node in self.nodes.values()
                    if node["workflow_run_id"] == workflow_run_id
                    and node["group_ref"] == group_ref
                ]
                rows.append(
                    {
                        "group_ref": group_ref,
                        "active_node_count": sum(
                            1 for node in nodes if node["active"] is True
                        ),
                        "active_compacted_node_count": sum(
                            1
                            for node in nodes
                            if node["active"] is True
                            and node["node_kind"] == "compacted"
                        ),
                    }
                )
            return rows

        if (
            "FROM draft_claim_compaction_nodes" in query
            and "AND node_ref = ANY" in query
        ):
            workflow_run_id = _str_arg(args[0])
            group_ref = _str_arg(args[1])
            node_refs = tuple(str(item) for item in _sequence_arg(args[2]))
            return [
                node
                for node in sorted(
                    self.nodes.values(),
                    key=lambda row: str(row["node_ref"]),
                )
                if node["workflow_run_id"] == workflow_run_id
                and node["group_ref"] == group_ref
                and node["node_ref"] in node_refs
            ]

        if (
            "FROM draft_claim_compaction_nodes" in query
            and "WHERE node_ref = ANY" in query
        ):
            node_refs = tuple(str(item) for item in _sequence_arg(args[0]))
            return [
                node
                for node in sorted(
                    self.nodes.values(),
                    key=lambda row: str(row["node_ref"]),
                )
                if node["node_ref"] in node_refs
            ]

        if "FROM draft_claim_compaction_nodes" in query:
            workflow_run_id = _str_arg(args[0])
            group_ref = _str_arg(args[1])
            return [
                node
                for node in sorted(
                    self.nodes.values(),
                    key=lambda row: str(row["node_ref"]),
                )
                if node["workflow_run_id"] == workflow_run_id
                and node["group_ref"] == group_ref
            ]

        if "FROM draft_claim_compaction_node_sources" in query:
            node_refs = tuple(str(item) for item in _sequence_arg(args[0]))
            return [
                source
                for source in sorted(
                    self.sources.values(),
                    key=lambda row: (str(row["node_ref"]), str(row["source_ref"])),
                )
                if source["node_ref"] in node_refs
            ]

        if (
            "COUNT(*) FILTER" in query
            and "FROM draft_claim_compaction_comparisons" in query
        ):
            workflow_run_id = _str_arg(args[0])
            group_refs = sorted(
                {
                    str(comparison["group_ref"])
                    for comparison in self.comparisons.values()
                    if comparison["workflow_run_id"] == workflow_run_id
                }
            )
            rows: list[Mapping[str, object]] = []
            for group_ref in group_refs:
                comparisons = [
                    comparison
                    for comparison in self.comparisons.values()
                    if comparison["workflow_run_id"] == workflow_run_id
                    and comparison["group_ref"] == group_ref
                ]
                rows.append(
                    {
                        "group_ref": group_ref,
                        "pending_comparison_count": sum(
                            1
                            for comparison in comparisons
                            if comparison["status"] == "pending"
                        ),
                        "waiting_user_model_choice_comparison_count": sum(
                            1
                            for comparison in comparisons
                            if comparison["status"] == "waiting_user_model_choice"
                        ),
                    }
                )
            return rows

        if "FROM draft_claim_compaction_comparisons" in query:
            workflow_run_id = _str_arg(args[0])
            group_ref = _str_arg(args[1])
            return [
                comparison
                for comparison in sorted(
                    self.comparisons.values(),
                    key=lambda row: str(row["comparison_ref"]),
                )
                if comparison["workflow_run_id"] == workflow_run_id
                and comparison["group_ref"] == group_ref
            ]

        if "FROM draft_claim_compaction_rounds" in query:
            return []

        if "FROM execution_work_items" in query:
            return [
                {
                    "ready_work_item_count": 0,
                    "leased_work_item_count": 0,
                    "deferred_work_item_count": 0,
                    "retryable_failed_work_item_count": 0,
                    "completed_work_item_count": 0,
                    "terminal_failed_work_item_count": 0,
                    "active_work_item_count": 0,
                    "due_waiting_work_item_count": 0,
                }
            ]

        raise AssertionError(f"unexpected fetch query: {query}")


@pytest.mark.asyncio
async def test_seeds_raw_nodes_and_sources_idempotently() -> None:
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    raw_nodes = (
        build_initial_raw_node(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            observation_ref="claim-a",
            estimated_input_tokens=10,
        ),
        build_initial_raw_node(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            observation_ref="claim-b",
            estimated_input_tokens=11,
        ),
    )

    first = await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=raw_nodes,
        created_at=_now(),
    )
    second = await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=raw_nodes,
        created_at=_now(),
    )

    assert first.requested_node_count == 2
    assert first.inserted_node_count == 2
    assert first.requested_source_count == 2
    assert first.inserted_source_count == 2
    assert first.already_exists_count == 0
    assert len(connection.components) == 2
    assert second.inserted_node_count == 0
    assert second.inserted_source_count == 0
    assert second.already_exists_count == 4


@pytest.mark.asyncio
async def test_load_planner_state_returns_active_raw_nodes_and_sources() -> None:
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=(
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-a",
                estimated_input_tokens=10,
            ),
        ),
        created_at=_now(),
    )

    state = await repository.load_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
    )

    assert state is not None
    assert state.cluster_ref == "group-1"
    assert len(state.nodes) == 1
    assert state.nodes[0].active is True
    assert state.nodes[0].node_kind.value == "raw"
    assert state.nodes[0].source_claim_refs == ("claim-a",)
    assert state.nodes[0].sources[0].source_ref == "claim-a"


@pytest.mark.asyncio
async def test_reduced_rewrite_rejects_source_node_from_another_group() -> None:
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    connection.nodes["group-1-compacted"] = _compacted_node_row(
        node_ref="group-1-compacted",
        group_ref="group-1",
    )
    connection.nodes["group-2-compacted"] = _compacted_node_row(
        node_ref="group-2-compacted",
        group_ref="group-2",
    )

    with pytest.raises(ValueError, match="source compacted nodes are not available"):
        await repository.apply_reduced_rewrite_result(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            batch_ref="batch-1",
            work_item_id="work-1",
            round_index=1,
            source_node_refs=("group-1-compacted", "group-2-compacted"),
            rewrite=DraftClaimReducedRewriteOutput(
                key="merged",
                claim="Merged claim",
                triples=(_triple(),),
            ),
            created_at=_now(),
        )


def _compacted_node_row(
    *,
    node_ref: str,
    group_ref: str,
) -> dict[str, object]:
    return {
        "node_ref": node_ref,
        "workflow_run_id": "workflow-1",
        "group_ref": group_ref,
        "node_kind": "compacted",
        "active": True,
        "source_claim_refs": json.dumps((f"source-{node_ref}",)),
        "supersedes_node_refs": json.dumps(()),
        "estimated_input_tokens": 10,
        "compacted_key": f"key-{node_ref}",
        "compacted_claim": f"Compacted claim {node_ref}",
        "compacted_claim_kind": "definition",
        "compacted_granularity": "atomic",
        "compacted_merge_decision": "merged",
        "compacted_triples": json.dumps([_triple().to_json_dict()]),
        "compacted_payload": None,
    }


def _str_arg(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("arg must be str")
    return value


def _bool_arg(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("arg must be bool")
    return value


def _int_arg(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("arg must be int")
    return value


def _sequence_arg(value: object) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise TypeError("arg must be list")
    return tuple(value)


@pytest.mark.asyncio
async def test_apply_compacted_claims_result_creates_active_compacted_node_idempotently() -> (
    None
):
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=(
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-a",
                estimated_input_tokens=10,
            ),
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-b",
                estimated_input_tokens=10,
            ),
        ),
        created_at=_now(),
    )

    first = await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        compacted_claims=(_compacted_claim(("claim-a", "claim-b")),),
        created_at=_now(),
    )
    second = await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        compacted_claims=(_compacted_claim(("claim-a", "claim-b")),),
        created_at=_now(),
    )

    state = await repository.load_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
    )

    assert first.inserted_node_count == 1
    assert first.superseded_node_count == 2
    assert first.inserted_source_count == 2
    assert first.inserted_comparison_count == 1
    assert second.inserted_node_count == 0
    assert second.inserted_source_count == 0
    assert second.inserted_comparison_count == 0
    assert second.superseded_node_count == 0
    assert len(connection.nodes) == 3
    assert len(connection.sources) == 4
    assert len(connection.comparisons) == 1
    assert len(connection.components) == 3
    assert state is not None
    active_nodes = tuple(node for node in state.nodes if node.active)
    inactive_nodes = tuple(node for node in state.nodes if not node.active)
    assert len(active_nodes) == 1
    assert active_nodes[0].node_kind is DraftClaimCompactionNodeKind.COMPACTED
    assert active_nodes[0].source_claim_refs == ("claim-a", "claim-b")
    assert active_nodes[0].compacted_key == "refund_support"
    assert active_nodes[0].compacted_claim == "Product supports refunds."
    assert active_nodes[0].estimated_input_tokens > 0
    assert active_nodes[0].compacted_triples == (_triple(),)
    assert active_nodes[0].compacted_claim_kind == "capability"
    assert active_nodes[0].compacted_granularity == "atomic"
    assert active_nodes[0].compacted_merge_decision == "merged"
    assert active_nodes[0].compacted_payload is not None
    assert active_nodes[0].compacted_payload["possible_questions"] == ["Q1", "Q2"]
    assert active_nodes[0].compacted_payload["exclusion_scope"] == "not X"
    assert active_nodes[0].compacted_payload["evidence_block"] == "E1"
    assert len(inactive_nodes) == 2
    assert state.comparisons[0].status.value == "merged"
    assert state.comparisons[0].result_node_ref == active_nodes[0].node_ref


@pytest.mark.asyncio
async def test_apply_compacted_claims_result_marks_distinct_outputs_not_merged() -> (
    None
):
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    raw_nodes = tuple(
        build_initial_raw_node(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            observation_ref=claim_ref,
            estimated_input_tokens=10,
        )
        for claim_ref in ("claim-1", "claim-2", "claim-3", "claim-4")
    )
    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=raw_nodes,
        created_at=_now(),
    )

    await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        compacted_claims=(
            _compacted_claim(("claim-1",)),
            _compacted_claim(("claim-2",)),
            _compacted_claim(("claim-3", "claim-4")),
        ),
        compared_node_refs=tuple(node.node_ref for node in raw_nodes),
        created_at=_now(),
    )

    state = await repository.load_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
    )

    assert state is not None
    active_nodes = state.active_nodes()
    assert len(active_nodes) == 3
    active_refs = {node.node_ref for node in active_nodes}
    not_merged_pairs = {
        comparison.pair_key
        for comparison in state.comparisons
        if comparison.status is DraftClaimCompactionComparisonStatus.NOT_MERGED
    }
    assert not_merged_pairs == {
        tuple(sorted(pair)) for pair in combinations(active_refs, 2)
    }
    decision = DraftClaimCompactionReductionPlannerPolicy().plan_next_step(state)
    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE


@pytest.mark.asyncio
async def test_not_merged_lineage_survives_reload_after_mixed_merge() -> None:
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)

    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=(
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-a",
                estimated_input_tokens=10,
            ),
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-b",
                estimated_input_tokens=10,
            ),
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-c",
                estimated_input_tokens=10,
            ),
        ),
        created_at=_now(),
    )

    raw_a = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-a",
    )
    raw_b = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-b",
    )
    raw_c = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-c",
    )

    await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        compacted_claims=(
            _compacted_claim(("claim-a",)),
            _compacted_claim(("claim-c",)),
        ),
        compared_node_refs=(raw_a, raw_c),
        created_at=_now(),
    )

    compacted_a = compacted_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        source_claim_refs=("claim-a",),
    )

    await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-2",
        work_item_id="work-item-2",
        round_index=1,
        compacted_claims=(_compacted_claim(("claim-a", "claim-b")),),
        compared_node_refs=(compacted_a, raw_b),
        created_at=_now(),
    )

    state = await repository.load_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
    )

    assert state is not None
    active_node_refs = {node.node_ref for node in state.active_nodes()}
    assert active_node_refs == {
        compacted_claim_node_ref(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            source_claim_refs=("claim-a", "claim-b"),
        ),
        compacted_claim_node_ref(
            workflow_run_id="workflow-1",
            group_ref="group-1",
            source_claim_refs=("claim-c",),
        ),
    }
    assert any(
        comparison.status is DraftClaimCompactionComparisonStatus.NOT_MERGED
        for comparison in state.comparisons
    )

    decision = DraftClaimCompactionReductionPlannerPolicy().plan_next_step(state)

    assert decision.work_type is DraftClaimCompactionNextWorkItemType.DONE
    assert decision.node_refs == ()


@pytest.mark.asyncio
async def test_apply_reduced_rewrite_result_merges_active_compacted_nodes_idempotently() -> (
    None
):
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    compacted_a = _active_compacted_node_row("compacted-a", ("claim-a", "claim-x"))
    compacted_b = _active_compacted_node_row("compacted-b", ("claim-b", "claim-x"))
    connection.nodes[compacted_a["node_ref"]] = compacted_a
    connection.nodes[compacted_b["node_ref"]] = compacted_b

    first = await repository.apply_reduced_rewrite_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=1,
        source_node_refs=("compacted-a", "compacted-b"),
        rewrite=DraftClaimReducedRewriteOutput(
            key="merged_refund_support",
            claim="Product supports refund workflows.",
            triples=(_triple(),),
        ),
        created_at=_now(),
    )
    second = await repository.apply_reduced_rewrite_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=1,
        source_node_refs=("compacted-a", "compacted-b"),
        rewrite=DraftClaimReducedRewriteOutput(
            key="merged_refund_support",
            claim="Product supports refund workflows.",
            triples=(_triple(),),
        ),
        created_at=_now(),
    )

    state = await repository.load_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
    )

    assert first.inserted_node_count == 1
    assert first.superseded_node_count == 2
    assert first.inserted_source_count == 2
    assert first.inserted_comparison_count == 1
    assert second.inserted_node_count == 0
    assert second.inserted_source_count == 0
    assert second.inserted_comparison_count == 0
    assert second.superseded_node_count == 0
    assert len(connection.nodes) == 3
    assert len(connection.sources) == 2
    assert len(connection.comparisons) == 1
    assert len(connection.components) >= 1
    assert state is not None
    active_nodes = tuple(node for node in state.nodes if node.active)
    assert len(active_nodes) == 1
    assert active_nodes[0].source_claim_refs == ("claim-a", "claim-b", "claim-x")
    assert active_nodes[0].supersedes_node_refs == ("compacted-a", "compacted-b")
    assert active_nodes[0].compacted_payload is not None
    assert active_nodes[0].compacted_payload["key"] == "merged_refund_support"
    assert (
        active_nodes[0].compacted_payload["claim"]
        == "Product supports refund workflows."
    )
    assert active_nodes[0].compacted_payload["possible_questions"] == [
        "Question compacted-a",
        "Question compacted-b",
    ]
    assert active_nodes[0].compacted_payload["exclusion_scope"] == (
        "not compacted-a\nnot compacted-b"
    )
    assert active_nodes[0].compacted_payload["evidence_block"] == (
        "Evidence compacted-a\n\nEvidence compacted-b"
    )
    assert state.comparisons[0].status.value == "merged"


def _compacted_claim(
    source_refs: tuple[str, ...],
) -> EnrichedDraftClaimCompactionOutputClaim:
    return EnrichedDraftClaimCompactionOutputClaim(
        key="refund_support",
        claim="Product supports refunds.",
        claim_kind="capability",
        granularity="atomic",
        source_claim_refs=source_refs,
        triples=(_triple(),),
        merge_decision="merged" if len(source_refs) > 1 else "unmerged",
        possible_questions=("Q1", "Q2"),
        exclusion_scope="not X",
        evidence_block="E1",
    )


def _triple() -> DraftClaimCompactionTriple:
    return DraftClaimCompactionTriple(
        subject="Product",
        predicate="has_capability",
        object="refunds",
        qualifiers=(),
    )


def _active_compacted_node_row(
    node_ref: str,
    source_claim_refs: tuple[str, ...],
) -> dict[str, object]:
    source_claim_refs_list = list(source_claim_refs)
    payload = {
        "key": node_ref,
        "claim": node_ref,
        "claim_kind": "capability",
        "granularity": "atomic",
        "source_claim_refs": source_claim_refs_list,
        "triples": [],
        "merge_decision": "merged",
        "possible_questions": [f"Question {node_ref}"],
        "exclusion_scope": f"not {node_ref}",
        "evidence_block": f"Evidence {node_ref}",
    }
    return {
        "node_ref": node_ref,
        "workflow_run_id": "workflow-1",
        "group_ref": "group-1",
        "node_kind": "compacted",
        "active": True,
        "source_claim_refs": source_claim_refs_list,
        "supersedes_node_refs": [],
        "estimated_input_tokens": 0,
        "compacted_key": node_ref,
        "compacted_claim": node_ref,
        "compacted_claim_kind": "capability",
        "compacted_granularity": "atomic",
        "compacted_merge_decision": "merged",
        "compacted_triples": [],
        "compacted_payload": payload,
    }


def _optional_str_arg(value: object) -> str | None:
    if value is None:
        return None
    return _str_arg(value)


@pytest.mark.asyncio
async def test_summarize_compaction_progress_completes_from_lineage_comparisons() -> (
    None
):
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)

    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        raw_nodes=(
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-a",
                estimated_input_tokens=10,
            ),
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-1",
                observation_ref="claim-b",
                estimated_input_tokens=10,
            ),
        ),
        created_at=_now(),
    )

    raw_a = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-a",
    )
    raw_b = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-b",
    )

    await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        compacted_claims=(
            _compacted_claim(("claim-a",)),
            _compacted_claim(("claim-b",)),
        ),
        compared_node_refs=(raw_a, raw_b),
        created_at=_now(),
    )

    summary = await repository.summarize_compaction_progress(
        workflow_run_id="workflow-1",
    )

    assert summary.active_component_count == 2
    assert summary.component_incompatibility_count == 0
    assert summary.done_group_count == 1
    assert summary.to_payload()["active_component_count"] == 2
    assert summary.to_payload()["component_incompatibility_count"] == 0


@pytest.mark.asyncio
async def test_summarize_compaction_progress_counts_done_and_active_groups() -> None:
    connection = FakeReductionStateConnection()
    repository = PostgresDraftClaimCompactionReductionStateRepository(connection)
    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-done",
        raw_nodes=(
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-done",
                observation_ref="claim-a",
                estimated_input_tokens=10,
            ),
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-done",
                observation_ref="claim-b",
                estimated_input_tokens=10,
            ),
        ),
        created_at=_now(),
    )
    await repository.apply_compacted_claims_result(
        workflow_run_id="workflow-1",
        group_ref="group-done",
        batch_ref="batch-1",
        work_item_id="work-item-1",
        round_index=0,
        compacted_claims=(_compacted_claim(("claim-a", "claim-b")),),
        created_at=_now(),
    )
    await repository.seed_initial_planner_state(
        workflow_run_id="workflow-1",
        group_ref="group-active",
        raw_nodes=(
            build_initial_raw_node(
                workflow_run_id="workflow-1",
                group_ref="group-active",
                observation_ref="claim-c",
                estimated_input_tokens=10,
            ),
        ),
        created_at=_now(),
    )

    summary = await repository.summarize_compaction_progress(
        workflow_run_id="workflow-1",
    )

    assert summary.group_count == 2
    assert summary.done_group_count == 1
    assert summary.active_group_count == 1
    assert summary.waiting_user_model_choice_group_count == 0
    assert summary.active_node_count == 2
    assert summary.pending_comparison_count == 0
    assert summary.active_component_count == 2
    assert summary.component_incompatibility_count == 0

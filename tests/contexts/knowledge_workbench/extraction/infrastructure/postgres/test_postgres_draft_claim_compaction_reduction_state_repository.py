from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionTriple,
    DraftClaimReducedRewriteOutput,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNodeKind,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_reduction_state_repository import (
    PostgresDraftClaimCompactionReductionStateRepository,
    build_initial_raw_node,
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

    async def execute(self, query: str, *args: object) -> object:
        if "INSERT INTO draft_claim_compaction_nodes" in query:
            node_ref = _str_arg(args[0])
            if node_ref in self.nodes:
                return "INSERT 0 0"
            self.nodes[node_ref] = {
                "node_ref": node_ref,
                "workflow_run_id": _str_arg(args[1]),
                "group_ref": _str_arg(args[2]),
                "node_kind": _str_arg(args[3]),
                "active": _bool_arg(args[4]),
                "source_claim_refs": json.loads(_str_arg(args[5])),
                "supersedes_node_refs": json.loads(_str_arg(args[6])),
                "estimated_input_tokens": _int_arg(args[7]),
                "compacted_key": _optional_str_arg(args[8]) if len(args) > 10 else None,
                "compacted_claim": _optional_str_arg(args[9])
                if len(args) > 10
                else None,
                "compacted_triples": (
                    json.loads(_str_arg(args[10])) if len(args) > 10 else []
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
                "result_node_ref": _str_arg(args[6]),
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

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
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
    assert state is not None
    active_nodes = tuple(node for node in state.nodes if node.active)
    inactive_nodes = tuple(node for node in state.nodes if not node.active)
    assert len(active_nodes) == 1
    assert active_nodes[0].node_kind is DraftClaimCompactionNodeKind.COMPACTED
    assert active_nodes[0].source_claim_refs == ("claim-a", "claim-b")
    assert len(inactive_nodes) == 2
    assert state.comparisons[0].status.value == "merged"
    assert state.comparisons[0].result_node_ref == active_nodes[0].node_ref


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
    assert state is not None
    active_nodes = tuple(node for node in state.nodes if node.active)
    assert len(active_nodes) == 1
    assert active_nodes[0].source_claim_refs == ("claim-a", "claim-b", "claim-x")
    assert active_nodes[0].supersedes_node_refs == ("compacted-a", "compacted-b")
    assert state.comparisons[0].status.value == "merged"


def _compacted_claim(source_refs: tuple[str, ...]) -> DraftClaimCompactionOutputClaim:
    return DraftClaimCompactionOutputClaim(
        key="refund_support",
        claim="Product supports refunds.",
        claim_kind="capability",
        granularity="atomic",
        source_claim_refs=source_refs,
        triples=(_triple(),),
        merge_decision="merged" if len(source_refs) > 1 else "unmerged",
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
    return {
        "node_ref": node_ref,
        "workflow_run_id": "workflow-1",
        "group_ref": "group-1",
        "node_kind": "compacted",
        "active": True,
        "source_claim_refs": list(source_claim_refs),
        "supersedes_node_refs": [],
        "estimated_input_tokens": 0,
        "compacted_key": node_ref,
        "compacted_claim": node_ref,
        "compacted_triples": [],
    }


def _optional_str_arg(value: object) -> str | None:
    if value is None:
        return None
    return _str_arg(value)

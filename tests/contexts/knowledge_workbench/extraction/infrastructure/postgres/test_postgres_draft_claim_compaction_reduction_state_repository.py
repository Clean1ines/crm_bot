from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

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
            return []

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

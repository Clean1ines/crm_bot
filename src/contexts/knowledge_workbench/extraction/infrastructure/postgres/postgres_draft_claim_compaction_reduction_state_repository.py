from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionComparison,
    DraftClaimCompactionComparisonStatus,
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionNodeSource,
    DraftClaimCompactionPlannerState,
    DraftClaimCompactionRound,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStatePersistenceResult,
    DraftClaimCompactionReductionStateRepositoryPort,
)


class DraftClaimCompactionReductionStateConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...
    async def execute(self, query: str, *args: object) -> object: ...


class PostgresDraftClaimCompactionReductionStateRepository(
    DraftClaimCompactionReductionStateRepositoryPort
):
    def __init__(
        self,
        connection: DraftClaimCompactionReductionStateConnectionLike,
    ) -> None:
        self._connection = connection

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        node_rows = await self._connection.fetch(
            """
            SELECT node_ref, node_kind, active, source_claim_refs,
                   supersedes_node_refs, estimated_input_tokens
            FROM draft_claim_compaction_nodes
            WHERE workflow_run_id = $1 AND group_ref = $2
            ORDER BY node_ref
            """,
            workflow_run_id,
            group_ref,
        )
        if not node_rows:
            return None

        source_rows = await self._connection.fetch(
            """
            SELECT node_ref, source_ref, source_kind
            FROM draft_claim_compaction_node_sources
            WHERE node_ref = ANY($1::text[])
            ORDER BY node_ref, source_ref
            """,
            [str(row["node_ref"]) for row in node_rows],
        )
        sources_by_node = _sources_by_node(source_rows)

        comparison_rows = await self._connection.fetch(
            """
            SELECT left_node_ref, right_node_ref, status, result_node_ref, round_index
            FROM draft_claim_compaction_comparisons
            WHERE workflow_run_id = $1 AND group_ref = $2
            ORDER BY round_index, created_at, comparison_ref
            """,
            workflow_run_id,
            group_ref,
        )
        comparisons = tuple(_comparison(row) for row in comparison_rows)

        round_rows = await self._connection.fetch(
            """
            SELECT round_index
            FROM draft_claim_compaction_rounds
            WHERE workflow_run_id = $1 AND group_ref = $2
            ORDER BY round_index
            """,
            workflow_run_id,
            group_ref,
        )
        rounds = tuple(
            DraftClaimCompactionRound(
                round_index=_int(row, "round_index"),
                comparisons=tuple(
                    comparison
                    for comparison in comparisons
                    if _comparison_round(comparison_rows, comparison)
                    == _int(
                        row,
                        "round_index",
                    )
                ),
            )
            for row in round_rows
        )

        return DraftClaimCompactionPlannerState(
            cluster_ref=group_ref,
            nodes=tuple(_node(row, sources_by_node) for row in node_rows),
            comparisons=comparisons,
            rounds=rounds,
        )

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes: tuple[DraftClaimCompactionNode, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        inserted_nodes = 0
        inserted_sources = 0

        for node in raw_nodes:
            if node.node_kind is not DraftClaimCompactionNodeKind.RAW:
                raise ValueError("initial planner state can only seed raw nodes")
            if _inserted(
                await self._connection.execute(
                    """
                    INSERT INTO draft_claim_compaction_nodes
                    (node_ref, workflow_run_id, group_ref, node_kind, active,
                     source_claim_refs, supersedes_node_refs, estimated_input_tokens,
                     created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10)
                    ON CONFLICT (node_ref) DO NOTHING
                    """,
                    node.node_ref,
                    workflow_run_id,
                    group_ref,
                    node.node_kind.value,
                    node.active,
                    json.dumps(list(node.source_claim_refs), sort_keys=True),
                    json.dumps(list(node.supersedes_node_refs), sort_keys=True),
                    node.estimated_input_tokens,
                    created_at,
                    created_at,
                )
            ):
                inserted_nodes += 1

            for source in node.sources:
                if _inserted(
                    await self._connection.execute(
                        """
                        INSERT INTO draft_claim_compaction_node_sources
                        (node_ref, source_ref, source_kind, created_at)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT (node_ref, source_ref) DO NOTHING
                        """,
                        node.node_ref,
                        source.source_ref,
                        source.source_kind.value,
                        created_at,
                    )
                ):
                    inserted_sources += 1

        requested_sources = sum(len(node.sources) for node in raw_nodes)
        requested_total = len(raw_nodes) + requested_sources
        inserted_total = inserted_nodes + inserted_sources
        return DraftClaimCompactionReductionStatePersistenceResult(
            requested_node_count=len(raw_nodes),
            inserted_node_count=inserted_nodes,
            requested_source_count=requested_sources,
            inserted_source_count=inserted_sources,
            requested_comparison_count=0,
            inserted_comparison_count=0,
            already_exists_count=requested_total - inserted_total,
        )


def raw_node_ref(
    *,
    workflow_run_id: str,
    group_ref: str,
    observation_ref: str,
) -> str:
    _text(workflow_run_id, "workflow_run_id")
    _text(group_ref, "group_ref")
    _text(observation_ref, "observation_ref")
    return f"raw:{workflow_run_id}:{group_ref}:{observation_ref}"


def build_initial_raw_node(
    *,
    workflow_run_id: str,
    group_ref: str,
    observation_ref: str,
    estimated_input_tokens: int,
) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=raw_node_ref(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            observation_ref=observation_ref,
        ),
        node_kind=DraftClaimCompactionNodeKind.RAW,
        source_claim_refs=(observation_ref,),
        sources=(
            DraftClaimCompactionNodeSource(
                source_ref=observation_ref,
                source_kind=DraftClaimCompactionNodeKind.RAW,
            ),
        ),
        active=True,
        estimated_input_tokens=estimated_input_tokens,
    )


def _node(
    row: Mapping[str, object],
    sources_by_node: Mapping[str, tuple[DraftClaimCompactionNodeSource, ...]],
) -> DraftClaimCompactionNode:
    node_ref = _str(row, "node_ref")
    return DraftClaimCompactionNode(
        node_ref=node_ref,
        node_kind=DraftClaimCompactionNodeKind(_str(row, "node_kind")),
        source_claim_refs=_json_text_tuple(
            row["source_claim_refs"], "source_claim_refs"
        ),
        sources=sources_by_node.get(node_ref, ()),
        active=_bool(row, "active"),
        supersedes_node_refs=_json_text_tuple(
            row["supersedes_node_refs"],
            "supersedes_node_refs",
        ),
        estimated_input_tokens=_int(row, "estimated_input_tokens"),
    )


def _sources_by_node(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, tuple[DraftClaimCompactionNodeSource, ...]]:
    mutable: dict[str, list[DraftClaimCompactionNodeSource]] = {}
    for row in rows:
        node_ref = _str(row, "node_ref")
        mutable.setdefault(node_ref, []).append(
            DraftClaimCompactionNodeSource(
                source_ref=_str(row, "source_ref"),
                source_kind=DraftClaimCompactionNodeKind(_str(row, "source_kind")),
            )
        )
    return {node_ref: tuple(sources) for node_ref, sources in mutable.items()}


def _comparison(row: Mapping[str, object]) -> DraftClaimCompactionComparison:
    return DraftClaimCompactionComparison(
        left_node_ref=_str(row, "left_node_ref"),
        right_node_ref=_str(row, "right_node_ref"),
        status=DraftClaimCompactionComparisonStatus(_str(row, "status")),
        result_node_ref=_optional_str(row, "result_node_ref"),
    )


def _comparison_round(
    rows: Sequence[Mapping[str, object]],
    comparison: DraftClaimCompactionComparison,
) -> int:
    for row in rows:
        if (
            _str(row, "left_node_ref") == comparison.left_node_ref
            and _str(row, "right_node_ref") == comparison.right_node_ref
            and _str(row, "status") == comparison.status.value
        ):
            return _int(row, "round_index")
    raise KeyError("comparison round not found")


def _json_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    parsed: object
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, Sequence) or isinstance(parsed, (str, bytes, bytearray)):
        raise TypeError(f"{field_name} must be json array")
    result: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise TypeError(f"{field_name} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str when set")
    return value


def _int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _bool(row: Mapping[str, object], key: str) -> bool:
    value = row[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _inserted(status: object) -> bool:
    text = str(status)
    return text.endswith(" 1") or text == "INSERT 1"

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    compacted_claim_node_ref,
    comparison_ref,
    ordered_pair,
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionTriple,
    DraftClaimCompactionTriplePredicate,
    DraftClaimReducedRewriteOutput,
)
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
    DraftClaimCompactionApplyPersistenceResult,
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
                   supersedes_node_refs, estimated_input_tokens,
                   compacted_key, compacted_claim, compacted_triples
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
        del batch_ref, work_item_id
        inserted_nodes = 0
        inserted_sources = 0
        inserted_comparisons = 0
        superseded_nodes = 0
        requested_nodes = len(compacted_claims)
        requested_sources = 0
        requested_comparisons = 0

        for claim in compacted_claims:
            node_ref = compacted_claim_node_ref(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                source_claim_refs=claim.source_claim_refs,
            )
            raw_node_refs = tuple(
                raw_claim_node_ref(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                    observation_ref=source_ref,
                )
                for source_ref in claim.source_claim_refs
            )

            if _inserted(
                await self._connection.execute(
                    """
                    INSERT INTO draft_claim_compaction_nodes
                    (node_ref, workflow_run_id, group_ref, node_kind, active,
                     source_claim_refs, supersedes_node_refs, estimated_input_tokens,
                     compacted_key, compacted_claim, compacted_triples,
                     created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10,$11::jsonb,$12,$13)
                    ON CONFLICT (node_ref) DO NOTHING
                    """,
                    node_ref,
                    workflow_run_id,
                    group_ref,
                    DraftClaimCompactionNodeKind.COMPACTED.value,
                    True,
                    json.dumps(list(claim.source_claim_refs), sort_keys=True),
                    json.dumps(list(raw_node_refs), sort_keys=True),
                    0,
                    claim.key,
                    claim.claim,
                    _triples_json(claim.triples),
                    created_at,
                    created_at,
                )
            ):
                inserted_nodes += 1

            for source_ref in claim.source_claim_refs:
                requested_sources += 1
                if _inserted(
                    await self._connection.execute(
                        """
                        INSERT INTO draft_claim_compaction_node_sources
                        (node_ref, source_ref, source_kind, created_at)
                        VALUES ($1,$2,$3,$4)
                        ON CONFLICT (node_ref, source_ref) DO NOTHING
                        """,
                        node_ref,
                        source_ref,
                        DraftClaimCompactionNodeKind.RAW.value,
                        created_at,
                    )
                ):
                    inserted_sources += 1

            superseded_nodes += _affected(
                await self._connection.execute(
                    """
                    UPDATE draft_claim_compaction_nodes
                    SET active = false, updated_at = $1
                    WHERE node_ref = ANY($2::text[]) AND active = true
                    """,
                    created_at,
                    list(raw_node_refs),
                )
            )

            for left, right in _node_ref_pairs(raw_node_refs):
                requested_comparisons += 1
                if await self._insert_merged_comparison(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                    round_index=round_index,
                    left_node_ref=left,
                    right_node_ref=right,
                    result_node_ref=node_ref,
                    created_at=created_at,
                ):
                    inserted_comparisons += 1

        requested_total = requested_nodes + requested_sources + requested_comparisons
        inserted_total = inserted_nodes + inserted_sources + inserted_comparisons
        return DraftClaimCompactionApplyPersistenceResult(
            inserted_node_count=inserted_nodes,
            updated_node_count=superseded_nodes,
            inserted_source_count=inserted_sources,
            inserted_comparison_count=inserted_comparisons,
            superseded_node_count=superseded_nodes,
            already_exists_count=requested_total - inserted_total,
        )

    async def apply_reduced_rewrite_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        source_node_refs: tuple[str, ...],
        rewrite: DraftClaimReducedRewriteOutput,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del batch_ref, work_item_id
        source_nodes = await self._load_nodes_by_ref(source_node_refs)
        if len(source_nodes) != len(set(source_node_refs)):
            raise ValueError("source compacted nodes are not available")

        union_source_claim_refs = _dedupe_sorted(
            source_ref for node in source_nodes for source_ref in node.source_claim_refs
        )
        node_ref = compacted_claim_node_ref(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            source_claim_refs=union_source_claim_refs,
        )
        inserted_nodes = 0
        inserted_sources = 0
        inserted_comparisons = 0

        if _inserted(
            await self._connection.execute(
                """
                INSERT INTO draft_claim_compaction_nodes
                (node_ref, workflow_run_id, group_ref, node_kind, active,
                 source_claim_refs, supersedes_node_refs, estimated_input_tokens,
                 compacted_key, compacted_claim, compacted_triples,
                 created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10,$11::jsonb,$12,$13)
                ON CONFLICT (node_ref) DO NOTHING
                """,
                node_ref,
                workflow_run_id,
                group_ref,
                DraftClaimCompactionNodeKind.COMPACTED.value,
                True,
                json.dumps(list(union_source_claim_refs), sort_keys=True),
                json.dumps(list(source_node_refs), sort_keys=True),
                0,
                rewrite.key,
                rewrite.claim,
                _triples_json(rewrite.triples),
                created_at,
                created_at,
            )
        ):
            inserted_nodes += 1

        for source_node_ref in source_node_refs:
            if _inserted(
                await self._connection.execute(
                    """
                    INSERT INTO draft_claim_compaction_node_sources
                    (node_ref, source_ref, source_kind, created_at)
                    VALUES ($1,$2,$3,$4)
                    ON CONFLICT (node_ref, source_ref) DO NOTHING
                    """,
                    node_ref,
                    source_node_ref,
                    DraftClaimCompactionNodeKind.COMPACTED.value,
                    created_at,
                )
            ):
                inserted_sources += 1

        superseded_nodes = _affected(
            await self._connection.execute(
                """
                UPDATE draft_claim_compaction_nodes
                SET active = false, updated_at = $1
                WHERE node_ref = ANY($2::text[]) AND active = true
                """,
                created_at,
                list(source_node_refs),
            )
        )

        for left, right in _node_ref_pairs(source_node_refs):
            if await self._insert_merged_comparison(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                round_index=round_index,
                left_node_ref=left,
                right_node_ref=right,
                result_node_ref=node_ref,
                created_at=created_at,
            ):
                inserted_comparisons += 1

        requested_total = (
            1 + len(source_node_refs) + len(_node_ref_pairs(source_node_refs))
        )
        inserted_total = inserted_nodes + inserted_sources + inserted_comparisons
        return DraftClaimCompactionApplyPersistenceResult(
            inserted_node_count=inserted_nodes,
            updated_node_count=superseded_nodes,
            inserted_source_count=inserted_sources,
            inserted_comparison_count=inserted_comparisons,
            superseded_node_count=superseded_nodes,
            already_exists_count=requested_total - inserted_total,
        )

    async def _load_nodes_by_ref(
        self,
        node_refs: tuple[str, ...],
    ) -> tuple[DraftClaimCompactionNode, ...]:
        if not node_refs:
            raise ValueError("node_refs must be non-empty")
        rows = await self._connection.fetch(
            """
            SELECT node_ref, node_kind, active, source_claim_refs,
                   supersedes_node_refs, estimated_input_tokens,
                   compacted_key, compacted_claim, compacted_triples
            FROM draft_claim_compaction_nodes
            WHERE node_ref = ANY($1::text[])
            ORDER BY node_ref
            """,
            list(node_refs),
        )
        source_rows = await self._connection.fetch(
            """
            SELECT node_ref, source_ref, source_kind
            FROM draft_claim_compaction_node_sources
            WHERE node_ref = ANY($1::text[])
            ORDER BY node_ref, source_ref
            """,
            [str(row["node_ref"]) for row in rows],
        )
        sources_by_node = _sources_by_node(source_rows)
        return tuple(_node(row, sources_by_node) for row in rows)

    async def _insert_merged_comparison(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        round_index: int,
        left_node_ref: str,
        right_node_ref: str,
        result_node_ref: str,
        created_at: datetime,
    ) -> bool:
        left, right = ordered_pair(left_node_ref, right_node_ref)
        return _inserted(
            await self._connection.execute(
                """
                INSERT INTO draft_claim_compaction_comparisons
                (comparison_ref, workflow_run_id, group_ref, left_node_ref,
                 right_node_ref, status, result_node_ref, round_index,
                 created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (workflow_run_id, group_ref, left_node_ref, right_node_ref, round_index)
                DO NOTHING
                """,
                comparison_ref(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                    round_index=round_index,
                    left_node_ref=left,
                    right_node_ref=right,
                ),
                workflow_run_id,
                group_ref,
                left,
                right,
                DraftClaimCompactionComparisonStatus.MERGED.value,
                result_node_ref,
                round_index,
                created_at,
                created_at,
            )
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
    return raw_claim_node_ref(
        workflow_run_id=workflow_run_id,
        group_ref=group_ref,
        observation_ref=observation_ref,
    )


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
        compacted_key=_optional_str(row, "compacted_key"),
        compacted_claim=_optional_str(row, "compacted_claim"),
        compacted_triples=_triples(row.get("compacted_triples", [])),
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


def _triples(value: object) -> tuple[DraftClaimCompactionTriple, ...]:
    parsed: object
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if parsed is None:
        return ()
    if not isinstance(parsed, Sequence) or isinstance(
        parsed,
        (str, bytes, bytearray),
    ):
        raise TypeError("compacted_triples must be json array")
    triples: list[DraftClaimCompactionTriple] = []
    for item in parsed:
        if not isinstance(item, Mapping):
            raise TypeError("compacted_triples items must be objects")
        triples.append(
            DraftClaimCompactionTriple(
                subject=_mapping_str(item, "subject"),
                predicate=DraftClaimCompactionTriplePredicate(
                    _mapping_str(item, "predicate"),
                ),
                object=_mapping_str(item, "object"),
                qualifiers=_mapping_str_tuple(item.get("qualifiers", [])),
            )
        )
    return tuple(triples)


def _mapping_str(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str")
    return value


def _mapping_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError("qualifiers must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError("qualifiers must contain str")
        result.append(item)
    return tuple(result)


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


def _triples_json(triples: tuple) -> str:
    return json.dumps(
        [triple.to_json_dict() for triple in triples],
        sort_keys=True,
    )


def _node_ref_pairs(node_refs: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    ordered = tuple(sorted(node_refs))
    pairs: list[tuple[str, str]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            pairs.append((left, right))
    return tuple(pairs)


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _affected(status: object) -> int:
    text = str(status)
    try:
        return int(text.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0

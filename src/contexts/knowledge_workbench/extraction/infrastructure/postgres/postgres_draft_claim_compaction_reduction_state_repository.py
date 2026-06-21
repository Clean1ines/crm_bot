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
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionClaimKind,
    DraftClaimCompactionGranularity,
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionTriple,
    DraftClaimCompactionTriplePredicate,
    DraftClaimReducedRewriteOutput,
)
from src.contexts.knowledge_workbench.extraction.application.models.enriched_draft_claim_compaction_output import (
    EnrichedDraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionComparison,
    DraftClaimCompactionComparisonStatus,
    DraftClaimCompactionComponent,
    DraftClaimCompactionComponentIncompatibility,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionNodeReadModel,
    DraftClaimCompactionNodeSource,
    DraftClaimCompactionPlannerState,
    DraftClaimCompactionRound,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_reduction_planner_policy import (
    DraftClaimCompactionReductionPlannerPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionApplyPersistenceResult,
    DraftClaimCompactionReductionStatePersistenceResult,
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue
from src.contexts.knowledge_workbench.document_segmentation.domain.segmentation_budget import (
    estimate_tokens_roughly,
)


class DraftClaimCompactionReductionStateConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...
    async def execute(self, query: str, *args: object) -> object: ...
    async def fetchval(self, query: str, *args: object) -> object: ...


class PostgresDraftClaimCompactionReductionStateRepository(
    DraftClaimCompactionReductionStateRepositoryPort
):
    def __init__(
        self,
        connection: DraftClaimCompactionReductionStateConnectionLike,
    ) -> None:
        self._connection = connection

    async def summarize_compaction_progress(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCompactionProgressSummary:
        node_rows = await self._connection.fetch(
            """
            SELECT group_ref,
                   COUNT(*) FILTER (WHERE active = true) AS active_node_count,
                   COUNT(*) FILTER (
                       WHERE active = true AND node_kind = 'raw'
                   ) AS active_raw_node_count,
                   COUNT(*) FILTER (
                       WHERE active = true AND node_kind = 'compacted'
                   ) AS active_compacted_node_count
            FROM draft_claim_compaction_nodes
            WHERE workflow_run_id = $1
            GROUP BY group_ref
            ORDER BY group_ref
            """,
            workflow_run_id,
        )
        # Comparisons are an audit log of concrete LLM pair attempts.
        # Components/incompatibilities below are the semantic reduction state.
        comparison_rows = await self._connection.fetch(
            """
            SELECT group_ref,
                   COUNT(*) FILTER (WHERE status = 'pending') AS pending_comparison_count,
                   COUNT(*) FILTER (
                       WHERE status = 'waiting_user_model_choice'
                   ) AS waiting_user_model_choice_comparison_count
            FROM draft_claim_compaction_comparisons
            WHERE workflow_run_id = $1
            GROUP BY group_ref
            ORDER BY group_ref
            """,
            workflow_run_id,
        )
        component_rows = await self._connection.fetch(
            """
            SELECT group_ref,
                   COUNT(*) FILTER (WHERE active = true) AS active_component_count
            FROM draft_claim_compaction_components
            WHERE workflow_run_id = $1
            GROUP BY group_ref
            ORDER BY group_ref
            """,
            workflow_run_id,
        )
        incompatibility_rows = await self._connection.fetch(
            """
            SELECT group_ref,
                   COUNT(*) AS component_incompatibility_count
            FROM draft_claim_compaction_component_incompatibilities
            WHERE workflow_run_id = $1
            GROUP BY group_ref
            ORDER BY group_ref
            """,
            workflow_run_id,
        )

        work_item_rows = await self._connection.fetch(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'ready') AS ready_work_item_count,
                COUNT(*) FILTER (WHERE status = 'leased') AS leased_work_item_count,
                COUNT(*) FILTER (WHERE status = 'deferred') AS deferred_work_item_count,
                COUNT(*) FILTER (
                    WHERE status = 'retryable_failed'
                ) AS retryable_failed_work_item_count,
                COUNT(*) FILTER (
                    WHERE status = 'completed'
                ) AS completed_work_item_count,
                COUNT(*) FILTER (
                    WHERE status = 'terminal_failed'
                ) AS terminal_failed_work_item_count,
                COUNT(*) FILTER (
                    WHERE status IN (
                        'ready',
                        'leased',
                        'deferred',
                        'retryable_failed'
                    )
                ) AS active_work_item_count,
                COUNT(*) FILTER (
                    WHERE status = 'ready'
                       OR (
                           status IN ('deferred', 'retryable_failed')
                           AND (
                               next_attempt_at IS NULL
                               OR next_attempt_at <= now()
                           )
                       )
                ) AS due_waiting_work_item_count,
                MIN(next_attempt_at) FILTER (
                    WHERE status IN ('deferred', 'retryable_failed')
                      AND next_attempt_at > now()
                ) AS next_due_at
            FROM execution_work_items
            WHERE work_kind = 'knowledge_workbench.draft_claim_compaction'
              AND work_item_id LIKE $1
            """,
            f"claim-compaction:{workflow_run_id}:%",
        )
        work_item_counts = work_item_rows[0] if work_item_rows else {}

        node_counts = {_str(row, "group_ref"): row for row in node_rows}
        comparison_counts = {_str(row, "group_ref"): row for row in comparison_rows}
        component_counts = {_str(row, "group_ref"): row for row in component_rows}
        incompatibility_counts = {
            _str(row, "group_ref"): row for row in incompatibility_rows
        }
        group_refs = tuple(
            sorted(
                set(node_counts)
                | set(comparison_counts)
                | set(component_counts)
                | set(incompatibility_counts)
            )
        )

        planner = DraftClaimCompactionReductionPlannerPolicy()

        done_group_count = 0
        waiting_group_count = 0
        active_node_count = 0
        pending_comparison_count = 0
        active_component_count = 0
        component_incompatibility_count = 0

        for group_ref in group_refs:
            node_row = node_counts.get(group_ref, {})
            comparison_row = comparison_counts.get(group_ref, {})
            component_row = component_counts.get(group_ref, {})
            incompatibility_row = incompatibility_counts.get(group_ref, {})

            group_active_node_count = _optional_int(node_row, "active_node_count")
            group_active_raw_node_count = _optional_int(
                node_row,
                "active_raw_node_count",
            )
            group_active_compacted_node_count = _optional_int(
                node_row,
                "active_compacted_node_count",
            )
            group_pending_comparison_count = _optional_int(
                comparison_row,
                "pending_comparison_count",
            )
            group_waiting_comparison_count = _optional_int(
                comparison_row,
                "waiting_user_model_choice_comparison_count",
            )
            group_active_component_count = _optional_int(
                component_row,
                "active_component_count",
            )
            group_component_incompatibility_count = _optional_int(
                incompatibility_row,
                "component_incompatibility_count",
            )

            active_node_count += group_active_node_count
            pending_comparison_count += group_pending_comparison_count
            active_component_count += group_active_component_count
            component_incompatibility_count += group_component_incompatibility_count

            if group_waiting_comparison_count > 0:
                waiting_group_count += 1
                continue

            if group_active_raw_node_count > 0:
                continue
            if group_active_compacted_node_count != group_active_node_count:
                continue

            planner_state = await self.load_planner_state(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
            )
            if planner_state is None:
                continue

            planner_decision = planner.plan_next_step(planner_state)
            if planner_decision.work_type is DraftClaimCompactionNextWorkItemType.DONE:
                done_group_count += 1

        group_count = len(group_refs)
        active_group_count = group_count - done_group_count - waiting_group_count
        if active_group_count < 0:
            active_group_count = 0

        return DraftClaimCompactionProgressSummary(
            workflow_run_id=workflow_run_id,
            group_count=group_count,
            done_group_count=done_group_count,
            waiting_user_model_choice_group_count=waiting_group_count,
            active_group_count=active_group_count,
            active_node_count=active_node_count,
            pending_comparison_count=pending_comparison_count,
            active_component_count=active_component_count,
            component_incompatibility_count=component_incompatibility_count,
            active_work_item_count=_optional_int(
                work_item_counts,
                "active_work_item_count",
            ),
            completed_work_item_count=_optional_int(
                work_item_counts,
                "completed_work_item_count",
            ),
            failed_work_item_count=(
                _optional_int(work_item_counts, "retryable_failed_work_item_count")
                + _optional_int(work_item_counts, "terminal_failed_work_item_count")
            ),
            ready_work_item_count=_optional_int(
                work_item_counts,
                "ready_work_item_count",
            ),
            leased_work_item_count=_optional_int(
                work_item_counts,
                "leased_work_item_count",
            ),
            deferred_work_item_count=_optional_int(
                work_item_counts,
                "deferred_work_item_count",
            ),
            retryable_failed_work_item_count=_optional_int(
                work_item_counts,
                "retryable_failed_work_item_count",
            ),
            terminal_failed_work_item_count=_optional_int(
                work_item_counts,
                "terminal_failed_work_item_count",
            ),
            due_waiting_work_item_count=_optional_int(
                work_item_counts,
                "due_waiting_work_item_count",
            ),
            next_due_at=_optional_datetime(work_item_counts, "next_due_at"),
        )

    async def list_compaction_nodes_for_workflow(
        self,
        *,
        workflow_run_id: str,
        group_ref: str | None,
        node_ref: str | None,
        active_only: bool,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimCompactionNodeReadModel, ...]:
        _read_model_require_text(workflow_run_id, "workflow_run_id")
        if group_ref is not None:
            _read_model_require_text(group_ref, "group_ref")
        if node_ref is not None:
            _read_model_require_text(node_ref, "node_ref")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be positive int")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be non-negative int")
        if not isinstance(active_only, bool):
            raise TypeError("active_only must be bool")

        rows = await self._connection.fetch(
            """
            SELECT workflow_run_id, group_ref, node_ref, node_kind, active,
                   source_claim_refs, supersedes_node_refs, estimated_input_tokens,
                   compacted_key, compacted_claim, compacted_claim_kind,
                   compacted_granularity, compacted_merge_decision,
                   created_at, updated_at
            FROM draft_claim_compaction_nodes
            WHERE workflow_run_id = $1
              AND ($2::text IS NULL OR group_ref = $2)
              AND ($3::text IS NULL OR node_ref = $3)
              AND ($4::boolean = false OR active = true)
            ORDER BY group_ref ASC, active DESC, updated_at DESC, node_ref ASC
            LIMIT $5 OFFSET $6
            """,
            workflow_run_id,
            group_ref,
            node_ref,
            active_only,
            limit,
            offset,
        )
        return tuple(_node_read_model(row) for row in rows)

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
                   compacted_key, compacted_claim, compacted_claim_kind,
                   compacted_granularity, compacted_merge_decision,
                   compacted_triples, compacted_payload
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

        component_rows = await self._connection.fetch(
            """
            SELECT component_ref, representative_node_ref, active,
                   source_claim_refs, supersedes_component_refs
            FROM draft_claim_compaction_components
            WHERE workflow_run_id = $1 AND group_ref = $2
            ORDER BY component_ref
            """,
            workflow_run_id,
            group_ref,
        )
        incompatibility_rows = await self._connection.fetch(
            """
            SELECT left_component_ref, right_component_ref
            FROM draft_claim_compaction_component_incompatibilities
            WHERE workflow_run_id = $1 AND group_ref = $2
            ORDER BY left_component_ref, right_component_ref
            """,
            workflow_run_id,
            group_ref,
        )

        return DraftClaimCompactionPlannerState(
            cluster_ref=group_ref,
            nodes=tuple(_node(row, sources_by_node) for row in node_rows),
            comparisons=comparisons,
            rounds=rounds,
            components=tuple(_component(row) for row in component_rows),
            incompatibilities=tuple(
                _component_incompatibility(row) for row in incompatibility_rows
            ),
        )

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compacted_claims: tuple[EnrichedDraftClaimCompactionOutputClaim, ...],
        compared_node_refs: tuple[str, ...] = (),
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del batch_ref, work_item_id
        compared_node_refs = tuple(compared_node_refs)
        compared_nodes = await self._load_compared_nodes_for_apply(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            compared_node_refs=compared_node_refs,
        )
        compared_source_sets = _source_claim_refs_by_node_ref(compared_nodes)

        inserted_nodes = 0
        inserted_sources = 0
        inserted_comparisons = 0
        superseded_nodes = 0
        requested_nodes = len(compacted_claims)
        requested_sources = 0
        requested_comparisons = 0
        output_node_refs: list[str] = []

        for claim in compacted_claims:
            node_ref = compacted_claim_node_ref(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                source_claim_refs=claim.source_claim_refs,
            )
            output_node_refs.append(node_ref)
            fallback_raw_node_refs = tuple(
                raw_claim_node_ref(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                    observation_ref=source_ref,
                )
                for source_ref in claim.source_claim_refs
            )
            source_node_refs = _matched_source_node_refs_for_claim(
                claim_source_claim_refs=claim.source_claim_refs,
                compared_source_sets=compared_source_sets,
                fallback_raw_node_refs=fallback_raw_node_refs,
            )

            if _inserted(
                await self._connection.execute(
                    """
                    INSERT INTO draft_claim_compaction_nodes
                    (node_ref, workflow_run_id, group_ref, node_kind, active,
                     source_claim_refs, supersedes_node_refs, estimated_input_tokens,
                     compacted_key, compacted_claim, compacted_claim_kind,
                     compacted_granularity, compacted_merge_decision,
                     compacted_triples, compacted_payload, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10,$11,$12,$13,$14::jsonb,$15::jsonb,$16,$17)
                    ON CONFLICT (node_ref) DO NOTHING
                    """,
                    node_ref,
                    workflow_run_id,
                    group_ref,
                    DraftClaimCompactionNodeKind.COMPACTED.value,
                    True,
                    json.dumps(list(claim.source_claim_refs), sort_keys=True),
                    json.dumps(list(source_node_refs), sort_keys=True),
                    _estimated_compacted_claim_tokens(claim.to_json_dict()),
                    claim.key,
                    claim.claim,
                    claim.claim_kind.value,
                    claim.granularity.value,
                    claim.merge_decision.value,
                    _triples_json(claim.triples),
                    _payload_json(claim.to_json_dict()),
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
                    list(source_node_refs),
                )
            )

            await self._upsert_merged_component(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                result_node_ref=node_ref,
                source_node_refs=source_node_refs,
                source_claim_refs=claim.source_claim_refs,
                created_at=created_at,
            )
            for left, right in _node_ref_pairs(source_node_refs):
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

        for left_output, right_output in _node_ref_pairs(tuple(output_node_refs)):
            requested_comparisons += 1
            if await self._insert_not_merged_comparison(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                round_index=round_index,
                left_node_ref=left_output,
                right_node_ref=right_output,
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
        source_nodes = await self._load_nodes_by_ref(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            node_refs=source_node_refs,
        )
        if len(source_nodes) != len(set(source_node_refs)):
            raise ValueError("source compacted nodes are not available")

        union_source_claim_refs = _dedupe_sorted(
            source_ref for node in source_nodes for source_ref in node.source_claim_refs
        )
        inherited_claim = _inherited_reduced_claim(
            source_nodes=source_nodes,
            source_claim_refs=union_source_claim_refs,
            rewrite=rewrite,
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
                 compacted_key, compacted_claim, compacted_claim_kind,
                 compacted_granularity, compacted_merge_decision,
                 compacted_triples, compacted_payload, created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10,$11,$12,$13,$14::jsonb,$15::jsonb,$16,$17)
                ON CONFLICT (node_ref) DO NOTHING
                """,
                node_ref,
                workflow_run_id,
                group_ref,
                DraftClaimCompactionNodeKind.COMPACTED.value,
                True,
                json.dumps(list(union_source_claim_refs), sort_keys=True),
                json.dumps(list(source_node_refs), sort_keys=True),
                _estimated_compacted_claim_tokens(inherited_claim.to_json_dict()),
                inherited_claim.key,
                inherited_claim.claim,
                inherited_claim.claim_kind.value,
                inherited_claim.granularity.value,
                inherited_claim.merge_decision.value,
                _triples_json(inherited_claim.triples),
                _payload_json(inherited_claim.to_json_dict()),
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

        await self._upsert_merged_component(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            result_node_ref=node_ref,
            source_node_refs=source_node_refs,
            source_claim_refs=union_source_claim_refs,
            created_at=created_at,
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
        *,
        workflow_run_id: str,
        group_ref: str,
        node_refs: tuple[str, ...],
    ) -> tuple[DraftClaimCompactionNode, ...]:
        if not node_refs:
            raise ValueError("node_refs must be non-empty")
        rows = await self._connection.fetch(
            """
            SELECT node_ref, node_kind, active, source_claim_refs,
                   supersedes_node_refs, estimated_input_tokens,
                   compacted_key, compacted_claim, compacted_claim_kind,
                   compacted_granularity, compacted_merge_decision,
                   compacted_triples, compacted_payload
            FROM draft_claim_compaction_nodes
            WHERE workflow_run_id = $1
              AND group_ref = $2
              AND node_ref = ANY($3::text[])
            ORDER BY node_ref
            """,
            workflow_run_id,
            group_ref,
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

    async def _load_compared_nodes_for_apply(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        compared_node_refs: tuple[str, ...],
    ) -> tuple[DraftClaimCompactionNode, ...]:
        if not compared_node_refs:
            return ()
        return await self._load_nodes_by_ref(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            node_refs=compared_node_refs,
        )

    async def _insert_not_merged_comparison(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        round_index: int,
        left_node_ref: str,
        right_node_ref: str,
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
                DraftClaimCompactionComparisonStatus.NOT_MERGED.value,
                None,
                round_index,
                created_at,
                created_at,
            )
        )

    async def _upsert_initial_component(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        node: DraftClaimCompactionNode,
        created_at: datetime,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_components
            (component_ref, workflow_run_id, group_ref, representative_node_ref,
             active, source_claim_refs, supersedes_component_refs,
             created_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9)
            ON CONFLICT (component_ref) DO NOTHING
            """,
            component_ref_for_node(node.node_ref),
            workflow_run_id,
            group_ref,
            node.node_ref,
            True,
            json.dumps(list(node.source_claim_refs), sort_keys=True),
            json.dumps([], sort_keys=True),
            created_at,
            created_at,
        )

    async def _upsert_merged_component(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        result_node_ref: str,
        source_node_refs: tuple[str, ...],
        source_claim_refs: tuple[str, ...],
        created_at: datetime,
    ) -> None:
        source_component_refs = await self._active_component_refs_for_nodes(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            node_refs=source_node_refs,
        )
        result_component_ref = component_ref_for_node(result_node_ref)
        inherited_refs = await self._inherited_incompatible_component_refs(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            component_refs=source_component_refs,
        )

        await self._connection.execute(
            """
            UPDATE draft_claim_compaction_components
            SET active = false, updated_at = $1
            WHERE workflow_run_id = $2
              AND group_ref = $3
              AND component_ref = ANY($4::text[])
              AND active = true
            """,
            created_at,
            workflow_run_id,
            group_ref,
            list(source_component_refs),
        )
        await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_components
            (component_ref, workflow_run_id, group_ref, representative_node_ref,
             active, source_claim_refs, supersedes_component_refs,
             created_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9)
            ON CONFLICT (component_ref) DO UPDATE
            SET active = EXCLUDED.active,
                representative_node_ref = EXCLUDED.representative_node_ref,
                source_claim_refs = EXCLUDED.source_claim_refs,
                supersedes_component_refs = EXCLUDED.supersedes_component_refs,
                updated_at = EXCLUDED.updated_at
            """,
            result_component_ref,
            workflow_run_id,
            group_ref,
            result_node_ref,
            True,
            json.dumps(list(source_claim_refs), sort_keys=True),
            json.dumps(list(source_component_refs), sort_keys=True),
            created_at,
            created_at,
        )
        for inherited_ref in inherited_refs:
            if inherited_ref in source_component_refs:
                continue
            await self._insert_component_incompatibility(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                left_component_ref=result_component_ref,
                right_component_ref=inherited_ref,
                source_comparison_ref=None,
                created_at=created_at,
            )

    async def _insert_component_incompatibility(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        left_component_ref: str,
        right_component_ref: str,
        source_comparison_ref: str | None,
        created_at: datetime,
    ) -> None:
        if left_component_ref == right_component_ref:
            return
        left, right = ordered_pair(left_component_ref, right_component_ref)
        await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_component_incompatibilities
            (incompatibility_ref, workflow_run_id, group_ref,
             left_component_ref, right_component_ref, source_comparison_ref,
             created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT (workflow_run_id, group_ref, left_component_ref, right_component_ref)
            DO NOTHING
            """,
            component_incompatibility_ref(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                left_component_ref=left,
                right_component_ref=right,
            ),
            workflow_run_id,
            group_ref,
            left,
            right,
            source_comparison_ref,
            created_at,
        )

    async def _active_component_refs_for_nodes(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        node_refs: tuple[str, ...],
    ) -> tuple[str, ...]:
        refs = []
        for node_ref in node_refs:
            refs.append(
                await self._active_component_ref_for_node(
                    workflow_run_id=workflow_run_id,
                    group_ref=group_ref,
                    node_ref=node_ref,
                )
            )
        return _dedupe_sorted(refs)

    async def _active_component_ref_for_node(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        node_ref: str,
    ) -> str:
        row_value = await self._connection.fetchval(
            """
            SELECT component_ref
            FROM draft_claim_compaction_components
            WHERE workflow_run_id = $1
              AND group_ref = $2
              AND representative_node_ref = $3
              AND active = true
            ORDER BY updated_at DESC, component_ref
            LIMIT 1
            """,
            workflow_run_id,
            group_ref,
            node_ref,
        )
        if row_value is None:
            return component_ref_for_node(node_ref)
        return str(row_value)

    async def _inherited_incompatible_component_refs(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        component_refs: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not component_refs:
            return ()
        rows = await self._connection.fetch(
            """
            SELECT left_component_ref, right_component_ref
            FROM draft_claim_compaction_component_incompatibilities
            WHERE workflow_run_id = $1
              AND group_ref = $2
              AND (
                  left_component_ref = ANY($3::text[])
                  OR right_component_ref = ANY($3::text[])
              )
            ORDER BY left_component_ref, right_component_ref
            """,
            workflow_run_id,
            group_ref,
            list(component_refs),
        )
        inherited: list[str] = []
        component_set = set(component_refs)
        for row in rows:
            left = str(row["left_component_ref"])
            right = str(row["right_component_ref"])
            if left in component_set and right not in component_set:
                inherited.append(right)
            if right in component_set and left not in component_set:
                inherited.append(left)
        return _dedupe_sorted(inherited)

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

            await self._upsert_initial_component(
                workflow_run_id=workflow_run_id,
                group_ref=group_ref,
                node=node,
                created_at=created_at,
            )

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

    async def list_final_compacted_nodes_for_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[DraftClaimCompactionNode, ...]:
        rows = await self._connection.fetch(
            """
            SELECT node_ref, node_kind, active, source_claim_refs,
                   supersedes_node_refs, estimated_input_tokens,
                   compacted_key, compacted_claim, compacted_claim_kind,
                   compacted_granularity, compacted_merge_decision,
                   compacted_triples, compacted_payload
            FROM draft_claim_compaction_nodes
            WHERE workflow_run_id = $1
              AND active = true
              AND node_kind = 'compacted'
            ORDER BY group_ref, node_ref
            """,
            workflow_run_id,
        )
        if not rows:
            return ()

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

    async def count_active_raw_nodes(
        self,
        *,
        workflow_run_id: str,
    ) -> int:
        value = await self._connection.fetchval(
            """
            SELECT count(*)
            FROM draft_claim_compaction_nodes
            WHERE workflow_run_id = $1
              AND active = true
              AND node_kind = 'raw'
            """,
            workflow_run_id,
        )
        if not isinstance(value, int):
            raise ValueError("active raw node count must be int")
        return value


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


def _estimated_compacted_claim_tokens(payload: JsonObject) -> int:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return max(1, estimate_tokens_roughly(serialized))


def _node_read_model(row: Mapping[str, object]) -> DraftClaimCompactionNodeReadModel:
    return DraftClaimCompactionNodeReadModel(
        workflow_run_id=_read_model_text(row, "workflow_run_id"),
        group_ref=_read_model_text(row, "group_ref"),
        node_ref=_read_model_text(row, "node_ref"),
        node_kind=_read_model_text(row, "node_kind"),
        active=_read_model_bool(row, "active"),
        source_claim_refs=_read_model_json_text_tuple(row, "source_claim_refs"),
        supersedes_node_refs=_read_model_json_text_tuple(row, "supersedes_node_refs"),
        estimated_input_tokens=_read_model_int(row, "estimated_input_tokens"),
        compacted_key=_read_model_optional_text(row, "compacted_key"),
        compacted_claim=_read_model_optional_text(row, "compacted_claim"),
        compacted_claim_kind=_read_model_optional_text(row, "compacted_claim_kind"),
        compacted_granularity=_read_model_optional_text(row, "compacted_granularity"),
        compacted_merge_decision=_read_model_optional_text(
            row,
            "compacted_merge_decision",
        ),
        created_at=_read_model_datetime(row, "created_at"),
        updated_at=_read_model_datetime(row, "updated_at"),
    )


def _read_model_text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _read_model_optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text or null")
    return value


def _read_model_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be int")
    return value


def _read_model_bool(row: Mapping[str, object], key: str) -> bool:
    value = row[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _read_model_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _read_model_json_text_tuple(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = row[key]
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, list | tuple):
        raise ValueError(f"{key} must be JSON array")
    result: list[str] = []
    for item in decoded:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _read_model_require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


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
        compacted_claim_kind=_optional_str_if_present(row, "compacted_claim_kind"),
        compacted_granularity=_optional_str_if_present(row, "compacted_granularity"),
        compacted_merge_decision=_optional_str_if_present(
            row,
            "compacted_merge_decision",
        ),
        compacted_payload=_json_object_or_none(row.get("compacted_payload")),
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


def _inherited_reduced_claim(
    *,
    source_nodes: tuple[DraftClaimCompactionNode, ...],
    source_claim_refs: tuple[str, ...],
    rewrite: DraftClaimReducedRewriteOutput,
) -> EnrichedDraftClaimCompactionOutputClaim:
    payloads = tuple(_node_payload(node) for node in source_nodes)
    possible_questions = _dedupe_preserving_order(
        question
        for payload in payloads
        for question in _payload_text_tuple(payload, "possible_questions")
    )
    exclusion_scope_values = _dedupe_preserving_order(
        _payload_text(payload, "exclusion_scope", allow_empty=True)
        for payload in payloads
    )
    evidence_block_values = _dedupe_preserving_order(
        _payload_text(payload, "evidence_block", allow_empty=False)
        for payload in payloads
    )
    return EnrichedDraftClaimCompactionOutputClaim(
        key=rewrite.key,
        claim=rewrite.claim,
        claim_kind=_inherited_claim_kind(payloads),
        granularity=_inherited_granularity(payloads),
        source_claim_refs=source_claim_refs,
        triples=rewrite.triples,
        merge_decision=DraftClaimCompactionMergeDecision.MERGED,
        possible_questions=possible_questions,
        exclusion_scope="\n".join(exclusion_scope_values),
        evidence_block="\n\n".join(evidence_block_values),
    )


def _node_payload(node: DraftClaimCompactionNode) -> JsonObject:
    if node.compacted_payload is None:
        raise ValueError("source compacted nodes lack compacted_payload")
    return node.compacted_payload


def _inherited_claim_kind(
    payloads: tuple[JsonObject, ...],
) -> DraftClaimCompactionClaimKind:
    values = tuple(
        DraftClaimCompactionClaimKind(_payload_text(payload, "claim_kind"))
        for payload in payloads
    )
    if len(set(values)) != 1:
        raise ValueError("source compacted nodes have conflicting claim_kind")
    return values[0]


def _inherited_granularity(
    payloads: tuple[JsonObject, ...],
) -> DraftClaimCompactionGranularity:
    values = tuple(
        DraftClaimCompactionGranularity(_payload_text(payload, "granularity"))
        for payload in payloads
    )
    if len(set(values)) == 1:
        return values[0]
    return DraftClaimCompactionGranularity.COMPOSITE


def _payload_text_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"compacted_payload {key} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"compacted_payload {key} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _payload_text(
    payload: JsonObject,
    key: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"compacted_payload {key} must be str")
    stripped = value.strip()
    if not stripped and not allow_empty:
        raise ValueError(f"compacted_payload {key} must be non-empty str")
    return stripped


def _dedupe_preserving_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("dedupe values must contain str")
        stripped = value.strip()
        if not stripped:
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return tuple(result)


def _payload_json(payload: JsonObject) -> str:
    return json.dumps(payload, sort_keys=True)


def _json_object_or_none(value: object) -> JsonObject | None:
    if value is None:
        return None
    parsed: object
    if isinstance(value, str):
        parsed = json.loads(value)
    else:
        parsed = value
    if not isinstance(parsed, Mapping):
        raise TypeError("compacted_payload must be json object")
    result: JsonObject = {}
    for key, item in parsed.items():
        if not isinstance(key, str):
            raise TypeError("compacted_payload keys must be str")
        result[key] = _json_value(item)
    return result


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        result: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("json object keys must be str")
            result[key] = _json_value(item)
        return result
    raise TypeError("value must be JSON-compatible")


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


def _optional_str_if_present(row: Mapping[str, object], key: str) -> str | None:
    if key not in row:
        return None
    return _optional_str(row, key)


def _int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key, 0)
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


def _triples_json(triples: tuple[DraftClaimCompactionTriple, ...]) -> str:
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


def _source_claim_refs_by_node_ref(
    nodes: tuple[DraftClaimCompactionNode, ...],
) -> dict[str, tuple[str, ...]]:
    return {node.node_ref: tuple(sorted(node.source_claim_refs)) for node in nodes}


def _matched_source_node_refs_for_claim(
    *,
    claim_source_claim_refs: tuple[str, ...],
    compared_source_sets: Mapping[str, tuple[str, ...]],
    fallback_raw_node_refs: tuple[str, ...],
) -> tuple[str, ...]:
    claim_source_set = set(claim_source_claim_refs)
    matched_refs = tuple(
        node_ref
        for node_ref, source_claim_refs in sorted(compared_source_sets.items())
        if set(source_claim_refs).issubset(claim_source_set)
    )
    if matched_refs:
        return matched_refs
    return fallback_raw_node_refs


def _component(row: Mapping[str, object]) -> DraftClaimCompactionComponent:
    return DraftClaimCompactionComponent(
        component_ref=_str(row, "component_ref"),
        representative_node_ref=_str(row, "representative_node_ref"),
        active=_bool(row, "active"),
        source_claim_refs=_json_text_tuple(
            row["source_claim_refs"],
            "source_claim_refs",
        ),
        supersedes_component_refs=_json_text_tuple(
            row["supersedes_component_refs"],
            "supersedes_component_refs",
        ),
    )


def _component_incompatibility(
    row: Mapping[str, object],
) -> DraftClaimCompactionComponentIncompatibility:
    return DraftClaimCompactionComponentIncompatibility(
        left_component_ref=_str(row, "left_component_ref"),
        right_component_ref=_str(row, "right_component_ref"),
    )


def component_ref_for_node(node_ref: str) -> str:
    _text(node_ref, "node_ref")
    return f"component:{node_ref}"


def component_incompatibility_ref(
    *,
    workflow_run_id: str,
    group_ref: str,
    left_component_ref: str,
    right_component_ref: str,
) -> str:
    left, right = ordered_pair(left_component_ref, right_component_ref)
    return f"component-incompatibility:{workflow_run_id}:{group_ref}:{left}:{right}"


def _compacted_claims_merge_compared_nodes(
    *,
    compared_node_refs: tuple[str, str],
    compacted_claims: tuple[EnrichedDraftClaimCompactionOutputClaim, ...],
    workflow_run_id: str,
    group_ref: str,
) -> bool:
    compared_source_sets = tuple(
        _source_claim_refs_from_node_ref(node_ref) for node_ref in compared_node_refs
    )
    union_refs = _dedupe_sorted(
        source_ref for source_refs in compared_source_sets for source_ref in source_refs
    )
    for claim in compacted_claims:
        if tuple(sorted(claim.source_claim_refs)) == union_refs:
            return True
    return False


def _source_claim_refs_from_node_ref(node_ref: str) -> tuple[str, ...]:
    if node_ref.startswith("raw:"):
        return (node_ref.rsplit(":", 1)[-1],)
    return ()


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionBatchForDispatch,
    DraftClaimCompactionBatchReadModel,
    DraftClaimCompactionEdgeCandidate,
    DraftClaimCompactionGroupCandidate,
    DraftClaimCompactionGroupMemberReadModel,
    DraftClaimCompactionGroupReadModel,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanPersistenceResult,
    DraftClaimCompactionPlanRepositoryPort,
)


class DraftClaimCompactionPlanConnectionLike(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...
    async def execute(self, query: str, *args: object) -> object: ...


class PostgresDraftClaimCompactionPlanRepository(
    DraftClaimCompactionPlanRepositoryPort
):
    def __init__(self, connection: DraftClaimCompactionPlanConnectionLike) -> None:
        self._connection = connection

    async def list_cluster_groups_for_workflow(
        self,
        *,
        workflow_run_id: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimCompactionGroupReadModel, ...]:
        _require_non_empty_text(workflow_run_id, "workflow_run_id")
        _validate_page(limit=limit, offset=offset)
        rows = await self._connection.fetch(
            """
            SELECT group_ref, workflow_run_id, source_document_ref,
                   embedding_model_id, group_algorithm, group_threshold,
                   member_count, artifact_tokens, requires_split, created_at
            FROM draft_claim_compaction_groups
            WHERE workflow_run_id = $1
            ORDER BY created_at ASC, group_ref ASC
            LIMIT $2 OFFSET $3
            """,
            workflow_run_id,
            limit,
            offset,
        )
        return tuple(_group_read_model(row) for row in rows)

    async def list_cluster_batches_for_workflow(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[DraftClaimCompactionBatchReadModel, ...]:
        _require_non_empty_text(workflow_run_id, "workflow_run_id")
        rows = await self._connection.fetch(
            """
            SELECT batch_ref, workflow_run_id, group_ref, prompt_variant, model_id,
                   artifact_tokens, batch_status, member_count, created_at
            FROM draft_claim_compaction_batches
            WHERE workflow_run_id = $1
            ORDER BY group_ref ASC, created_at ASC, batch_ref ASC
            """,
            workflow_run_id,
        )
        return tuple(_batch_read_model(row) for row in rows)

    async def list_cluster_members_for_group(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimCompactionGroupMemberReadModel, ...]:
        _require_non_empty_text(workflow_run_id, "workflow_run_id")
        _require_non_empty_text(group_ref, "group_ref")
        _validate_page(limit=limit, offset=offset)
        rows = await self._connection.fetch(
            """
            SELECT gm.group_ref, gm.observation_ref, gm.embedding_ref,
                   gm.source_unit_ref, gm.member_rank, gm.member_kind, gm.created_at
            FROM draft_claim_compaction_group_members AS gm
            JOIN draft_claim_compaction_groups AS g
              ON g.group_ref = gm.group_ref
            WHERE g.workflow_run_id = $1
              AND gm.group_ref = $2
            ORDER BY gm.member_rank ASC, gm.observation_ref ASC
            LIMIT $3 OFFSET $4
            """,
            workflow_run_id,
            group_ref,
            limit,
            offset,
        )
        return tuple(_member_read_model(row) for row in rows)

    async def get_compaction_batch_by_ref(
        self,
        *,
        batch_ref: str,
    ) -> DraftClaimCompactionBatchForDispatch | None:
        rows = await self._connection.fetch(
            """
            SELECT b.batch_ref, b.workflow_run_id, b.group_ref, b.prompt_variant,
                   b.model_id, b.artifact_tokens,
                   COALESCE(
                       array_agg(gm.observation_ref ORDER BY gm.member_rank)
                       FILTER (WHERE gm.observation_ref IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS member_observation_refs
            FROM draft_claim_compaction_batches b
            LEFT JOIN draft_claim_compaction_group_members gm
                ON gm.group_ref = b.group_ref
            WHERE b.batch_ref = $1
            GROUP BY b.batch_ref, b.workflow_run_id, b.group_ref, b.prompt_variant,
                     b.model_id, b.artifact_tokens
            """,
            batch_ref,
        )
        if not rows:
            return None
        return _batch_for_dispatch(rows[0])

    async def list_claims_for_compaction_batch(
        self,
        *,
        batch_ref: str,
    ) -> tuple[DraftClaimForCompaction, ...]:
        rows = await self._connection.fetch(
            """
            SELECT e.embedding_ref, e.workflow_run_id, e.source_document_ref,
                   e.source_unit_ref, e.observation_ref, e.embedding_text,
                   e.embedding_model_id, e.dimensions, e.embedding,
                   o.claim, o.granularity, o.exclusion_scope,
                   COALESCE(array_agg(q.question ORDER BY q.ordinal)
                       FILTER (WHERE q.question IS NOT NULL), ARRAY[]::text[]) AS possible_questions,
                   gm.member_rank,
                   p.claim_index
            FROM draft_claim_compaction_batches b
            JOIN draft_claim_compaction_group_members gm
                ON gm.group_ref = b.group_ref
            JOIN draft_claim_embeddings e
                ON e.observation_ref = gm.observation_ref
            JOIN draft_claim_observations o
                ON o.observation_ref = e.observation_ref
            JOIN draft_claim_observation_provenance p
                ON p.observation_ref = e.observation_ref
            LEFT JOIN draft_claim_observation_possible_questions q
                ON q.observation_ref = e.observation_ref
            WHERE b.batch_ref = $1
            GROUP BY e.embedding_ref, e.workflow_run_id, e.source_document_ref,
                     e.source_unit_ref, e.observation_ref, e.embedding_text,
                     e.embedding_model_id, e.dimensions, e.embedding,
                     o.claim, o.granularity, o.exclusion_scope,
                     gm.member_rank, p.claim_index
            ORDER BY gm.member_rank, p.claim_index, e.observation_ref
            """,
            batch_ref,
        )
        return tuple(_claim(row) for row in rows)

    async def list_claims_for_compaction(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
    ) -> tuple[DraftClaimForCompaction, ...]:
        rows = await self._connection.fetch(
            """
            SELECT e.embedding_ref, e.workflow_run_id, e.source_document_ref,
                   e.source_unit_ref, e.observation_ref, e.embedding_text,
                   e.embedding_model_id, e.dimensions, e.embedding,
                   o.claim, o.granularity, o.exclusion_scope,
                   COALESCE(array_agg(q.question ORDER BY q.ordinal)
                       FILTER (WHERE q.question IS NOT NULL), ARRAY[]::text[]) AS possible_questions,
                   p.claim_index
            FROM draft_claim_embeddings e
            JOIN draft_claim_observations o ON o.observation_ref = e.observation_ref
            JOIN draft_claim_observation_provenance p ON p.observation_ref = e.observation_ref
            LEFT JOIN draft_claim_observation_possible_questions q ON q.observation_ref = e.observation_ref
            WHERE e.workflow_run_id = $1 AND e.embedding_model_id = $2
            GROUP BY e.embedding_ref, e.workflow_run_id, e.source_document_ref,
                     e.source_unit_ref, e.observation_ref, e.embedding_text,
                     e.embedding_model_id, e.dimensions, e.embedding,
                     o.claim, o.granularity, o.exclusion_scope, p.claim_index
            ORDER BY e.source_unit_ref, p.claim_index, e.observation_ref
            """,
            workflow_run_id,
            embedding_model_id,
        )
        return tuple(_claim(row) for row in rows)

    async def persist_compaction_plan(
        self,
        *,
        edges: tuple[DraftClaimCompactionEdgeCandidate, ...],
        groups: tuple[DraftClaimCompactionGroupCandidate, ...],
        batches: tuple[DraftClaimCompactionBatchCandidate, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionPlanPersistenceResult:
        inserted_edges = 0
        inserted_groups = 0
        inserted_members = 0
        inserted_batches = 0
        for edge in edges:
            if _inserted(await self._insert_edge(edge, created_at)):
                inserted_edges += 1
        for group in groups:
            if _inserted(await self._insert_group(group, created_at)):
                inserted_groups += 1
            for rank, observation_ref in enumerate(group.member_observation_refs):
                if _inserted(
                    await self._insert_member(group, observation_ref, rank, created_at)
                ):
                    inserted_members += 1
        for batch in batches:
            if _inserted(await self._insert_batch(batch, created_at)):
                inserted_batches += 1
        requested_members = sum(group.member_count for group in groups)
        requested_total = len(edges) + len(groups) + requested_members + len(batches)
        inserted_total = (
            inserted_edges + inserted_groups + inserted_members + inserted_batches
        )
        return DraftClaimCompactionPlanPersistenceResult(
            requested_edge_count=len(edges),
            inserted_edge_count=inserted_edges,
            requested_group_count=len(groups),
            inserted_group_count=inserted_groups,
            requested_member_count=requested_members,
            inserted_member_count=inserted_members,
            requested_batch_count=len(batches),
            inserted_batch_count=inserted_batches,
            already_exists_count=requested_total - inserted_total,
        )

    async def _insert_edge(
        self, edge: DraftClaimCompactionEdgeCandidate, created_at: datetime
    ) -> object:
        return await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_candidate_edges
            (edge_ref, workflow_run_id, source_document_ref, left_observation_ref,
             right_observation_ref, left_embedding_ref, right_embedding_ref,
             vector_score, lexical_score, question_overlap_score, exclusion_scope_score,
             granularity_score, combined_score, signals, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15)
            ON CONFLICT (workflow_run_id, left_observation_ref, right_observation_ref) DO NOTHING
            """,
            edge.edge_ref,
            edge.workflow_run_id,
            edge.source_document_ref,
            edge.left_observation_ref,
            edge.right_observation_ref,
            edge.left_embedding_ref,
            edge.right_embedding_ref,
            edge.vector_score,
            edge.lexical_score,
            edge.question_overlap_score,
            edge.exclusion_scope_score,
            edge.granularity_score,
            edge.combined_score,
            json.dumps(dict(edge.signals), sort_keys=True),
            created_at,
        )

    async def _insert_group(
        self, group: DraftClaimCompactionGroupCandidate, created_at: datetime
    ) -> object:
        return await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_groups
            (group_ref, workflow_run_id, source_document_ref, embedding_model_id,
             group_algorithm, group_threshold, member_count, artifact_tokens,
             requires_split, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (workflow_run_id, group_ref) DO NOTHING
            """,
            group.group_ref,
            group.workflow_run_id,
            group.source_document_ref,
            group.embedding_model_id,
            group.group_algorithm,
            group.group_threshold,
            group.member_count,
            group.artifact_tokens,
            group.requires_split,
            created_at,
        )

    async def _insert_member(
        self,
        group: DraftClaimCompactionGroupCandidate,
        observation_ref: str,
        rank: int,
        created_at: datetime,
    ) -> object:
        index = group.member_observation_refs.index(observation_ref)
        return await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_group_members
            (group_ref, observation_ref, embedding_ref, source_unit_ref, member_rank, member_kind, created_at)
            VALUES ($1,$2,$3,$4,$5,'draft_claim',$6)
            ON CONFLICT (group_ref, observation_ref) DO NOTHING
            """,
            group.group_ref,
            observation_ref,
            group.member_embedding_refs[index],
            group.member_source_unit_refs[index],
            rank,
            created_at,
        )

    async def _insert_batch(
        self, batch: DraftClaimCompactionBatchCandidate, created_at: datetime
    ) -> object:
        return await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_batches
            (batch_ref, workflow_run_id, group_ref, prompt_variant, model_id,
             artifact_tokens, batch_status, member_count, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'planned',$7,$8)
            ON CONFLICT (workflow_run_id, group_ref, batch_ref) DO NOTHING
            """,
            batch.batch_ref,
            batch.workflow_run_id,
            batch.group_ref,
            batch.prompt_variant,
            batch.model_id,
            batch.artifact_tokens,
            batch.member_count,
            created_at,
        )


def _group_read_model(row: Mapping[str, object]) -> DraftClaimCompactionGroupReadModel:
    return DraftClaimCompactionGroupReadModel(
        group_ref=_s(row, "group_ref"),
        workflow_run_id=_s(row, "workflow_run_id"),
        source_document_ref=_s(row, "source_document_ref"),
        embedding_model_id=_s(row, "embedding_model_id"),
        group_algorithm=_s(row, "group_algorithm"),
        group_threshold=_f(row, "group_threshold"),
        member_count=_i(row, "member_count"),
        artifact_tokens=_i(row, "artifact_tokens"),
        requires_split=_b(row, "requires_split"),
        created_at=_dt(row, "created_at"),
    )


def _batch_read_model(row: Mapping[str, object]) -> DraftClaimCompactionBatchReadModel:
    return DraftClaimCompactionBatchReadModel(
        batch_ref=_s(row, "batch_ref"),
        workflow_run_id=_s(row, "workflow_run_id"),
        group_ref=_s(row, "group_ref"),
        prompt_variant=_s(row, "prompt_variant"),
        model_id=_s(row, "model_id"),
        artifact_tokens=_i(row, "artifact_tokens"),
        batch_status=_s(row, "batch_status"),
        member_count=_i(row, "member_count"),
        created_at=_dt(row, "created_at"),
    )


def _member_read_model(
    row: Mapping[str, object],
) -> DraftClaimCompactionGroupMemberReadModel:
    return DraftClaimCompactionGroupMemberReadModel(
        group_ref=_s(row, "group_ref"),
        observation_ref=_s(row, "observation_ref"),
        embedding_ref=_s(row, "embedding_ref"),
        source_unit_ref=_s(row, "source_unit_ref"),
        member_rank=_i(row, "member_rank"),
        member_kind=_s(row, "member_kind"),
        created_at=_dt(row, "created_at"),
    )


def _batch_for_dispatch(
    row: Mapping[str, object],
) -> DraftClaimCompactionBatchForDispatch:
    return DraftClaimCompactionBatchForDispatch(
        batch_ref=_s(row, "batch_ref"),
        workflow_run_id=_s(row, "workflow_run_id"),
        group_ref=_s(row, "group_ref"),
        prompt_variant=_s(row, "prompt_variant"),
        model_id=_s(row, "model_id"),
        artifact_tokens=_i(row, "artifact_tokens"),
        member_observation_refs=_strings(row["member_observation_refs"]),
    )


def _claim(row: Mapping[str, object]) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=_s(row, "observation_ref"),
        embedding_ref=_s(row, "embedding_ref"),
        workflow_run_id=_s(row, "workflow_run_id"),
        source_document_ref=_s(row, "source_document_ref"),
        source_unit_ref=_s(row, "source_unit_ref"),
        claim=_s(row, "claim"),
        possible_questions=_strings(row["possible_questions"]),
        exclusion_scope=tuple(
            part.strip()
            for part in _s_allow_empty(row, "exclusion_scope").splitlines()
            if part.strip()
        ),
        granularity=_s(row, "granularity"),
        embedding_text=_s(row, "embedding_text"),
        embedding_model_id=_s(row, "embedding_model_id"),
        dimensions=_i(row, "dimensions"),
        vector=_vector(row["embedding"]),
    )


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _validate_page(*, limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be int")
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise TypeError("offset must be int")
    if offset < 0:
        raise ValueError("offset must be >= 0")


def _s(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str")
    return value


def _s_allow_empty(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    return value


def _i(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _f(row: Mapping[str, object], key: str) -> float:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _b(row: Mapping[str, object], key: str) -> bool:
    value = row[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _dt(row: Mapping[str, object], key: str):
    value = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("expected sequence")
    return tuple(str(item) for item in value if str(item).strip())


def _vector(value: object) -> tuple[float, ...]:
    if isinstance(value, str):
        return tuple(
            float(part.strip()) for part in value.strip("[]").split(",") if part.strip()
        )
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        raise TypeError("embedding must be sequence or pgvector string")
    return tuple(float(item) for item in value)


def _inserted(status: object) -> bool:
    text = str(status)
    return text.endswith(" 1") or text == "INSERT 1"

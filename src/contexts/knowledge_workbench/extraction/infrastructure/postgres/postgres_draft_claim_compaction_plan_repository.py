from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionEdgeCandidate,
    DraftClaimCompactionGroupCandidate,
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
            json.dumps(edge.signals, sort_keys=True),
            created_at,
        )

    async def _insert_group(
        self, group: DraftClaimCompactionGroupCandidate, created_at: datetime
    ) -> object:
        return await self._connection.execute(
            """
            INSERT INTO draft_claim_compaction_groups
            (group_ref, workflow_run_id, source_document_ref, embedding_model_id,
             group_algorithm, group_threshold, member_count, estimated_input_tokens,
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
            group.estimated_input_tokens,
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
             estimated_input_tokens, batch_status, member_count, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'planned',$7,$8)
            ON CONFLICT (workflow_run_id, group_ref, batch_ref) DO NOTHING
            """,
            batch.batch_ref,
            batch.workflow_run_id,
            batch.group_ref,
            batch.prompt_variant,
            batch.model_id,
            batch.estimated_input_tokens,
            batch.member_count,
            created_at,
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

from __future__ import annotations

from collections.abc import Sequence

import asyncpg

from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    CandidateCluster,
)
from src.infrastructure.db.repositories.knowledge_compiler_payloads import (
    answer_candidate_source_refs_payload,
    compiler_jsonb_array_payload,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import jsonb_object_payload
from src.utils.uuid_utils import ensure_uuid


def affected_row_count(command_result: str) -> int:
    try:
        return int(str(command_result).split()[-1])
    except (IndexError, ValueError):
        return 0


async def delete_raw_answer_candidates_for_batch(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    batch_id: str,
) -> int:
    result = await conn.execute(
        """
        DELETE FROM knowledge_answer_candidates
        WHERE project_id = $1
          AND document_id = $2
          AND metadata->>'stage' = 'stage_k_raw_extraction'
          AND metadata->>'batch_id' = $3
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        batch_id,
    )
    return affected_row_count(result)


async def upsert_answer_candidate(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    candidate: AnswerCandidate,
) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_answer_candidates (
            id,
            project_id,
            document_id,
            compiler_run_id,
            topic_key,
            title,
            candidate_answer,
            source_refs,
            confidence,
            status,
            rejection_reason,
            metadata
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8::jsonb,
            $9,
            $10,
            $11,
            $12::jsonb
        )
        ON CONFLICT (id)
        DO UPDATE SET
            topic_key = EXCLUDED.topic_key,
            title = EXCLUDED.title,
            candidate_answer = EXCLUDED.candidate_answer,
            source_refs = EXCLUDED.source_refs,
            confidence = EXCLUDED.confidence,
            status = EXCLUDED.status,
            rejection_reason = EXCLUDED.rejection_reason,
            metadata = EXCLUDED.metadata
        """,
        candidate.id,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        candidate.compiler_run_id,
        candidate.topic_key,
        candidate.title,
        candidate.candidate_answer,
        compiler_jsonb_array_payload(answer_candidate_source_refs_payload(candidate)),
        candidate.confidence,
        candidate.status.value,
        candidate.rejection_reason,
        jsonb_object_payload(candidate.metadata),
    )


async def upsert_answer_candidates(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    candidates: Sequence[AnswerCandidate],
) -> int:
    for candidate in candidates:
        await upsert_answer_candidate(
            conn,
            project_id=project_id,
            document_id=document_id,
            candidate=candidate,
        )
    return len(candidates)


async def upsert_candidate_cluster(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    cluster: CandidateCluster,
) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_candidate_clusters (
            id,
            project_id,
            document_id,
            compiler_run_id,
            cluster_key,
            topic,
            status,
            merge_strategy,
            merge_reason,
            metadata
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9,
            $10::jsonb
        )
        ON CONFLICT (id)
        DO UPDATE SET
            cluster_key = EXCLUDED.cluster_key,
            topic = EXCLUDED.topic,
            status = EXCLUDED.status,
            merge_strategy = EXCLUDED.merge_strategy,
            merge_reason = EXCLUDED.merge_reason,
            metadata = EXCLUDED.metadata
        """,
        cluster.id,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        cluster.compiler_run_id,
        cluster.cluster_key,
        cluster.topic,
        cluster.status.value,
        cluster.merge_strategy,
        cluster.merge_reason,
        jsonb_object_payload(cluster.metadata),
    )

    await conn.execute(
        """
        DELETE FROM knowledge_candidate_cluster_members
        WHERE cluster_id = $1
        """,
        cluster.id,
    )

    for candidate_index, candidate_id in enumerate(cluster.candidate_ids):
        await conn.execute(
            """
            INSERT INTO knowledge_candidate_cluster_members (
                cluster_id,
                candidate_id,
                candidate_index
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (cluster_id, candidate_id)
            DO UPDATE SET
                candidate_index = EXCLUDED.candidate_index
            """,
            cluster.id,
            candidate_id,
            candidate_index,
        )


async def upsert_candidate_clusters(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    clusters: Sequence[CandidateCluster],
) -> int:
    for cluster in clusters:
        await upsert_candidate_cluster(
            conn,
            project_id=project_id,
            document_id=document_id,
            cluster=cluster,
        )
    return len(clusters)

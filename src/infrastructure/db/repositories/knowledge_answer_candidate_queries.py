from __future__ import annotations

import asyncpg

from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    AnswerCandidateStatus,
)
from src.domain.project_plane.knowledge_views import KnowledgeAnswerCandidateSummaryView
from src.infrastructure.db.repositories.knowledge_db_codecs import (
    json_object_from_db,
    optional_float,
    source_refs_from_db,
)
from src.utils.uuid_utils import ensure_uuid


async def list_document_raw_answer_candidates(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
) -> tuple[AnswerCandidate, ...]:
    rows = await conn.fetch(
        """
        SELECT
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
            metadata,
            created_at
        FROM knowledge_answer_candidates
        WHERE project_id = $1
          AND document_id = $2
          AND metadata->>'stage' = 'stage_k_raw_extraction'
        ORDER BY (metadata->>'batch_index')::int,
                 (metadata->>'fragment_index')::int,
                 created_at
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
    )

    return tuple(
        AnswerCandidate(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            compiler_run_id=str(row["compiler_run_id"]),
            topic_key=str(row["topic_key"]),
            title=str(row["title"] or ""),
            candidate_answer=str(row["candidate_answer"] or ""),
            source_refs=source_refs_from_db(row["source_refs"]),
            confidence=optional_float(row["confidence"]),
            status=AnswerCandidateStatus(str(row["status"])),
            rejection_reason=str(row["rejection_reason"] or ""),
            metadata=json_object_from_db(row["metadata"]),
            created_at=row["created_at"],
        )
        for row in rows
    )


async def get_document_answer_candidate_summary(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
) -> KnowledgeAnswerCandidateSummaryView:
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*)::int AS total_count,
            COUNT(*) FILTER (
                WHERE metadata->>'stage' = 'stage_k_raw_extraction'
            )::int AS raw_count,
            COUNT(*) FILTER (
                WHERE metadata->>'stage' <> 'stage_k_raw_extraction'
                   OR metadata->>'stage' IS NULL
            )::int AS final_count,
            COUNT(*) FILTER (WHERE status = 'rejected')::int AS rejected_count,
            COUNT(*) FILTER (WHERE jsonb_array_length(source_refs) > 0)::int AS grounded_count
        FROM knowledge_answer_candidates
        WHERE project_id = $1
          AND document_id = $2
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
    )

    if row is None:
        return KnowledgeAnswerCandidateSummaryView()

    return KnowledgeAnswerCandidateSummaryView(
        total_count=int(row["total_count"] or 0),
        raw_count=int(row["raw_count"] or 0),
        final_count=int(row["final_count"] or 0),
        rejected_count=int(row["rejected_count"] or 0),
        grounded_count=int(row["grounded_count"] or 0),
    )

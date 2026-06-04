from __future__ import annotations

import json
from collections.abc import Mapping
import asyncpg

from src.domain.project_plane.json_types import JsonObject, JsonValue


class WorkbenchRagEvalEditRepository:
    """Workbench-backed RAG-eval edit action adapter.

    This is the current edit/review side for RAG eval. It stores action state in
    knowledge_edit_actions and mutates only the Workbench runtime retrieval
    projection for automatically executable safe actions.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_or_get_knowledge_edit_action(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        source_result_id: str,
        source_run_id: str,
        source_question_id: str,
        action_index: int,
        actor_user_id: str,
        action_type: str,
        target_entry_id: str | None,
        reason: str,
        payload: JsonObject,
    ) -> JsonObject:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_edit_actions (
                    id,
                    project_id,
                    document_id,
                    source_result_id,
                    source_run_id,
                    source_question_id,
                    action_index,
                    actor_user_id,
                    action_type,
                    target_entry_id,
                    reason,
                    payload,
                    status,
                    source_kind,
                    created_at,
                    updated_at
                )
                VALUES (
                    $1,
                    $2::uuid,
                    $3,
                    $4,
                    $5,
                    $6,
                    $7,
                    $8,
                    $9,
                    $10,
                    $11,
                    $12::jsonb,
                    'pending',
                    'rag_eval',
                    NOW(),
                    NOW()
                )
                ON CONFLICT (source_result_id, action_index) DO UPDATE SET
                    updated_at = knowledge_edit_actions.updated_at
                RETURNING *
                """,
                action_id,
                project_id,
                document_id,
                source_result_id,
                source_run_id,
                source_question_id,
                action_index,
                actor_user_id,
                action_type,
                target_entry_id,
                reason,
                _json(payload),
            )
        return _row_to_json_object_required(row)

    async def mark_knowledge_edit_action_applied(
        self,
        action_id: str,
        *,
        result_payload: JsonObject | None = None,
    ) -> None:
        await self._mark_action(
            action_id,
            status="applied",
            error=None,
            result_payload=result_payload,
        )

    async def mark_knowledge_edit_action_rejected(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None:
        await self._mark_action(
            action_id,
            status="rejected",
            error=error,
            result_payload=result_payload,
        )

    async def mark_knowledge_edit_action_failed(
        self,
        action_id: str,
        *,
        error: str,
        result_payload: JsonObject | None = None,
    ) -> None:
        await self._mark_action(
            action_id,
            status="failed",
            error=error,
            result_payload=result_payload,
        )

    async def attach_question_to_entry(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
        question: str,
        reason: str,
        actor_user_id: str,
    ) -> None:
        normalized_question = " ".join(question.split())
        if not normalized_question:
            raise ValueError("attach_question_to_entry requires non-empty question")

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE knowledge_workbench_runtime_retrieval_entries
                SET
                    possible_questions = (
                        SELECT jsonb_agg(value)
                        FROM (
                            SELECT DISTINCT value
                            FROM jsonb_array_elements_text(
                                COALESCE(possible_questions, '[]'::jsonb)
                                || to_jsonb(ARRAY[$4::text])
                            ) AS q(value)
                            WHERE btrim(value) <> ''
                        ) AS deduped
                    ),
                    embedding_text = btrim(
                        concat_ws(
                            E'\n',
                            claim,
                            answer_text,
                            (
                                SELECT string_agg(value, E'\n')
                                FROM jsonb_array_elements_text(
                                    COALESCE(possible_questions, '[]'::jsonb)
                                    || to_jsonb(ARRAY[$4::text])
                                ) AS q(value)
                            )
                        )
                    ),
                    updated_at = NOW()
                WHERE project_id = $1::uuid
                  AND (runtime_entry_id = $2 OR fact_id = $2)
                  AND status = 'published'
                  AND visibility = 'runtime'
                """,
                project_id,
                target_entry_id,
                document_id,
                normalized_question,
            )

        if _command_count(result) <= 0:
            raise ValueError(
                f"Workbench runtime entry not found for attach_question_to_entry: {target_entry_id}"
            )

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE knowledge_workbench_runtime_retrieval_entries
                SET
                    embedding_text = btrim(
                        concat_ws(
                            E'\n',
                            claim,
                            answer_text,
                            (
                                SELECT string_agg(value, E'\n')
                                FROM jsonb_array_elements_text(
                                    COALESCE(possible_questions, '[]'::jsonb)
                                ) AS q(value)
                            ),
                            source_refs::text
                        )
                    ),
                    updated_at = NOW()
                WHERE project_id = $1::uuid
                  AND (runtime_entry_id = $2 OR fact_id = $2)
                  AND status = 'published'
                  AND visibility = 'runtime'
                """,
                project_id,
                target_entry_id,
            )

        if _command_count(result) <= 0:
            raise ValueError(
                f"Workbench runtime entry not found for rebuild_entry_embedding: {target_entry_id}"
            )

    async def _mark_action(
        self,
        action_id: str,
        *,
        status: str,
        error: str | None,
        result_payload: JsonObject | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE knowledge_edit_actions
                SET
                    status = $2,
                    error = $3,
                    result_payload = COALESCE($4::jsonb, result_payload),
                    updated_at = NOW()
                WHERE id = $1
                """,
                action_id,
                status,
                error,
                None if result_payload is None else _json(result_payload),
            )


def _json(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _row_to_json_object_required(row: object | None) -> JsonObject:
    if row is None:
        raise ValueError("knowledge edit action was not persisted")
    if not isinstance(row, Mapping):
        raise TypeError("knowledge edit action row must be mapping-like")

    payload: JsonObject = {}
    for key, value in row.items():
        if isinstance(key, str):
            payload[key] = _json_value(value)
    return payload


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def _command_count(result: str) -> int:
    try:
        return int(result.rsplit(" ", 1)[-1])
    except (IndexError, ValueError):
        return 0


__all__ = ["WorkbenchRagEvalEditRepository"]

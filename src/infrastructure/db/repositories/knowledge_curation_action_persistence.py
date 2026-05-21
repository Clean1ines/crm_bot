"""Persistence helpers for knowledge curation actions and entry version snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import asyncpg

from src.application.errors import ConflictError
from src.domain.project_plane.json_types import JsonObject
from src.infrastructure.db.repositories.knowledge_curation_mappers import (
    stage_h_entry_snapshot,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import json_object_from_db
from src.utils.uuid_utils import ensure_uuid


def jsonb_payload(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def jsonb_array_payload(values: Sequence[object]) -> str:
    return json.dumps(list(values), ensure_ascii=False, default=str)


def stable_payload_fingerprint(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), sort_keys=True, default=str)


async def create_or_get_result_action(
    conn: asyncpg.Connection,
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
    existing = await conn.fetchrow(
        """
        SELECT id, status
        FROM knowledge_edit_actions
        WHERE source_result_id = $1
          AND action_index = $2
        """,
        source_result_id,
        action_index,
    )
    if existing is not None:
        return {"id": str(existing["id"]), "status": str(existing["status"])}

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
            payload
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
            $10,
            $11,
            $12::jsonb
        )
        RETURNING id, status
        """,
        action_id,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        source_result_id,
        source_run_id,
        source_question_id,
        action_index,
        actor_user_id,
        action_type,
        ensure_uuid(target_entry_id) if target_entry_id else None,
        reason,
        jsonb_payload(payload),
    )

    if row is None:
        raise RuntimeError("Failed to create knowledge edit action")

    return {"id": str(row["id"]), "status": str(row["status"])}


async def mark_action_applied(
    conn: asyncpg.Connection,
    action_id: str,
    *,
    result_payload: JsonObject | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_edit_actions
        SET status = 'applied',
            error = '',
            result_payload = $2::jsonb,
            applied_at = COALESCE(applied_at, now()),
            updated_at = now()
        WHERE id = $1
        """,
        action_id,
        jsonb_payload(result_payload or {}),
    )


async def mark_action_rejected(
    conn: asyncpg.Connection,
    action_id: str,
    *,
    error: str,
    result_payload: JsonObject | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_edit_actions
        SET status = 'rejected',
            error = $2,
            result_payload = $3::jsonb,
            updated_at = now()
        WHERE id = $1
        """,
        action_id,
        error,
        jsonb_payload(result_payload or {}),
    )


async def mark_action_failed(
    conn: asyncpg.Connection,
    action_id: str,
    *,
    error: str,
    result_payload: JsonObject | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_edit_actions
        SET status = 'failed',
            error = $2,
            result_payload = $3::jsonb,
            updated_at = now()
        WHERE id = $1
        """,
        action_id,
        error,
        jsonb_payload(result_payload or {}),
    )


async def create_manual_curation_action(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    action_type: str,
    actor_user_id: str,
    target_entry_id: str | None,
    target_entry_ids: Sequence[str],
    reason: str,
    payload: Mapping[str, object],
    idempotency_key: str,
    source_kind: str,
) -> str:
    action_payload = dict(payload)
    if idempotency_key:
        existing = await conn.fetchrow(
            """
            SELECT id, payload, status, result_payload, error
            FROM knowledge_edit_actions
            WHERE project_id = $1
              AND document_id = $2
              AND source_kind = $3
              AND idempotency_key = $4
            """,
            ensure_uuid(project_id),
            ensure_uuid(document_id),
            source_kind,
            idempotency_key,
        )
        if existing is not None:
            existing_payload_fingerprint = stable_payload_fingerprint(
                json_object_from_db(existing["payload"])
            )
            requested_payload_fingerprint = stable_payload_fingerprint(action_payload)
            if existing_payload_fingerprint != requested_payload_fingerprint:
                raise ConflictError("idempotency_conflict")

            existing_status = str(existing["status"] or "")
            existing_id = str(existing["id"])
            if existing_status in {
                "applied",
                "applied_with_warning",
                "failed",
                "rejected",
            }:
                raise ConflictError(f"idempotency_replay:{existing_id}")
            raise ConflictError(f"action_in_progress:{existing_id}")

    action_id = (
        f"curation:{action_type}:{project_id}:{document_id}:"
        f"{idempotency_key or len(jsonb_payload(action_payload))}"
    )
    await conn.execute(
        """
        INSERT INTO knowledge_edit_actions (
            id,
            project_id,
            document_id,
            source_kind,
            source_id,
            idempotency_key,
            target_entry_id,
            target_entry_ids_json,
            actor_user_id,
            action_type,
            reason,
            payload
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11, $12::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        action_id,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        source_kind,
        target_entry_id or document_id,
        idempotency_key,
        ensure_uuid(target_entry_id) if target_entry_id else None,
        jsonb_array_payload(target_entry_ids),
        actor_user_id,
        action_type,
        reason,
        jsonb_payload(action_payload),
    )
    return action_id


async def load_existing_manual_curation_action(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    source_kind: str,
    idempotency_key: str,
    payload: Mapping[str, object],
) -> Mapping[str, object] | None:
    if not idempotency_key.strip():
        return None

    existing = await conn.fetchrow(
        """
        SELECT id, payload, status, result_payload, error
        FROM knowledge_edit_actions
        WHERE project_id = $1
          AND document_id = $2
          AND source_kind = $3
          AND idempotency_key = $4
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        source_kind,
        idempotency_key,
    )
    if existing is None:
        return None

    existing_payload_fingerprint = stable_payload_fingerprint(
        json_object_from_db(existing["payload"])
    )
    requested_payload_fingerprint = stable_payload_fingerprint(dict(payload))
    if existing_payload_fingerprint != requested_payload_fingerprint:
        raise ConflictError("idempotency_conflict")

    status = str(existing["status"] or "")
    action_id = str(existing["id"])
    if status in {"proposed", "in_progress"}:
        raise ConflictError(f"action_in_progress:{action_id}")

    return {
        "action_id": action_id,
        "status": status,
        "result_payload": json_object_from_db(existing["result_payload"]),
        "error": str(existing["error"] or ""),
    }


async def mark_action_completed_with_result(
    conn: asyncpg.Connection,
    action_id: str,
    *,
    status: str,
    error: str | None,
    result_payload: Mapping[str, object],
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_edit_actions
        SET status = $2,
            error = $3,
            result_payload = $4::jsonb,
            applied_at = COALESCE(applied_at, now()),
            updated_at = now()
        WHERE id = $1
        """,
        action_id,
        status,
        error,
        jsonb_payload(result_payload),
    )


async def write_version_snapshot(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
    project_id: str,
    document_id: str,
    action_id: str,
    before: asyncpg.Record,
    after: asyncpg.Record,
    from_version: int,
    to_version: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_entry_versions (
            entry_id, project_id, document_id, action_id, from_version, to_version,
            previous_snapshot, new_snapshot
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
        """,
        ensure_uuid(entry_id),
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        action_id,
        from_version,
        to_version,
        jsonb_payload(stage_h_entry_snapshot(before)),
        jsonb_payload(stage_h_entry_snapshot(after)),
    )


async def mark_action_applied_raw(conn: asyncpg.Connection, action_id: str) -> None:
    await conn.execute(
        "UPDATE knowledge_edit_actions SET status = 'applied', applied_at = COALESCE(applied_at, now()), updated_at = now() WHERE id = $1",
        action_id,
    )


async def mark_action_in_progress_raw(conn: asyncpg.Connection, action_id: str) -> None:
    await conn.execute(
        "UPDATE knowledge_edit_actions SET status = 'in_progress', updated_at = now() WHERE id = $1",
        action_id,
    )

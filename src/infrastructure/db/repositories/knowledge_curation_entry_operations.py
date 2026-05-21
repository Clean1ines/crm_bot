from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence

import asyncpg

from src.domain.project_plane.json_types import json_object_from_unknown
from src.application.errors import ConflictError, NotFoundError, ValidationError
from src.domain.project_plane.knowledge_curation import (
    KnowledgeEntryMergePreview,
    KnowledgeEntryMergeRequest,
    KnowledgeEntryPatch,
)
from src.domain.project_plane.knowledge_compilation import (
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate
from src.infrastructure.db.repositories.knowledge_curation_action_persistence import (
    mark_action_applied_raw,
    mark_action_in_progress_raw,
    write_version_snapshot,
)
from src.infrastructure.db.repositories.knowledge_curation_mappers import (
    stage_h_embedding_text,
    stage_h_json_object,
    stage_h_search_text,
    stage_h_text_list,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import (
    json_list_from_db,
    json_object_from_db,
)
from src.infrastructure.db.repositories.knowledge_entry_persistence import (
    delete_retrieval_surface,
    replace_entry_source_refs_from_payload,
    update_retrieval_surface_content,
    update_retrieval_surface_metadata,
    upsert_retrieval_surface_from_payload,
)
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.llm.embedding_service import embed_batch
from src.utils.uuid_utils import ensure_uuid


@dataclass(frozen=True)
class EntryMutationResult:
    action_id: str
    entry_id: str


@dataclass(frozen=True)
class ManualEntryMergeMutationResult:
    action_id: str
    parent_version: int
    replay_payload: Mapping[str, object] | None = None


ManualCurationActionCreator = Callable[..., Awaitable[str]]
ManualCurationActionLoader = Callable[..., Awaitable[Mapping[str, object] | None]]


_ENTRY_SELECT_COLUMNS = """
    id,
    project_id,
    document_id,
    compiler_run_id,
    stable_key,
    entry_kind,
    title,
    answer,
    status,
    visibility,
    version,
    compiler_version,
    embedding_text,
    embedding_text_version,
    enrichment,
    metadata
"""


async def _fetch_entry_by_id(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"""
        SELECT {_ENTRY_SELECT_COLUMNS}
        FROM knowledge_entries
        WHERE id = $1
        """,
        ensure_uuid(entry_id),
    )


async def _fetch_entry_for_update(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    entry_id: str,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        f"""
        SELECT {_ENTRY_SELECT_COLUMNS}
        FROM knowledge_entries
        WHERE id = $1
          AND project_id = $2
          AND document_id = $3
        FOR UPDATE
        """,
        ensure_uuid(entry_id),
        ensure_uuid(project_id),
        ensure_uuid(document_id),
    )


async def attach_question_to_entry(
    pool: asyncpg.Pool,
    *,
    action_id: str,
    project_id: str,
    document_id: str,
    target_entry_id: str,
    question: str,
    reason: str,
    actor_user_id: str,
) -> None:
    question_text = " ".join(question.strip().split())
    if not question_text:
        raise ValueError("attach_question_to_entry requires non-empty question")

    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await _fetch_entry_for_update(
                conn,
                project_id=project_id,
                document_id=document_id,
                entry_id=target_entry_id,
            )
            if before is None:
                raise NotFoundError("target knowledge entry not found")

            previous_version = int(before["version"])
            metadata = stage_h_json_object(before["metadata"])
            enrichment = stage_h_json_object(before["enrichment"])

            stage_h = stage_h_json_object(metadata.get("stage_h"))
            raw_attached = stage_h.get("attached_questions")
            attached: list[dict[str, object]] = []
            if isinstance(raw_attached, list):
                attached = [
                    {str(key): value for key, value in item.items()}
                    for item in raw_attached
                    if isinstance(item, dict)
                ]

            if not any(item.get("question") == question_text for item in attached):
                attached.append(
                    {
                        "question": question_text,
                        "action_id": action_id,
                        "reason": reason,
                        "actor_user_id": actor_user_id,
                    }
                )

            stage_h["attached_questions"] = attached
            metadata["stage_h"] = stage_h

            for key in ("questions", "positive_questions"):
                values = stage_h_text_list(enrichment.get(key))
                if question_text not in values:
                    values.append(question_text)
                enrichment[key] = values

            next_version = previous_version + 1

            await conn.execute(
                """
                UPDATE knowledge_entries
                SET enrichment = $2::jsonb,
                    metadata = $3::jsonb,
                    version = $4,
                    updated_at = now()
                WHERE id = $1
                """,
                ensure_uuid(target_entry_id),
                json.dumps(enrichment, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                next_version,
            )

            await update_retrieval_surface_metadata(
                conn,
                entry_id=target_entry_id,
                enrichment=enrichment,
                metadata=metadata,
            )

            after = await _fetch_entry_by_id(conn, entry_id=target_entry_id)
            if after is None:
                raise RuntimeError("target knowledge entry disappeared after update")

            await write_version_snapshot(
                conn,
                entry_id=target_entry_id,
                project_id=project_id,
                document_id=document_id,
                action_id=action_id,
                before=before,
                after=after,
                from_version=previous_version,
                to_version=next_version,
            )


async def rebuild_entry_embedding(
    pool: asyncpg.Pool,
    usage_repo: ModelUsageRepository,
    *,
    action_id: str,
    project_id: str,
    document_id: str,
    target_entry_id: str,
) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {_ENTRY_SELECT_COLUMNS}
            FROM knowledge_entries
            WHERE id = $1
              AND project_id = $2
              AND document_id = $3
            """,
            ensure_uuid(target_entry_id),
            ensure_uuid(project_id),
            ensure_uuid(document_id),
        )

    if row is None:
        raise NotFoundError("target knowledge entry not found")

    embedding_text = stage_h_embedding_text(row)
    if not embedding_text.strip():
        raise ValueError("cannot rebuild embedding from empty entry text")

    embedding_result = await embed_batch([embedding_text])
    if not embedding_result.embeddings:
        raise RuntimeError("embedding provider returned no vectors")

    if embedding_result.usage is not None:
        await usage_repo.record_event(
            ModelUsageEventCreate.from_measurement(
                project_id=project_id,
                source="knowledge_edit_action",
                measurement=embedding_result.usage,
                document_id=document_id,
            )
        )

    embedding_text_version = "entry_embedding_text_v2_stage_h"
    search_text = stage_h_search_text(
        title=str(row["title"]),
        answer=str(row["answer"]),
        embedding_text=embedding_text,
    )

    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await _fetch_entry_for_update(
                conn,
                project_id=project_id,
                document_id=document_id,
                entry_id=target_entry_id,
            )
            if before is None:
                raise NotFoundError("target knowledge entry not found")

            entry_version = int(before["version"])

            await conn.execute(
                """
                UPDATE knowledge_entries
                SET embedding_text = $2,
                    embedding_text_version = $3,
                    updated_at = now()
                WHERE id = $1
                """,
                ensure_uuid(target_entry_id),
                embedding_text,
                embedding_text_version,
            )

            source_refs_payload = await conn.fetchval(
                """
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'source_index', source_index,
                            'quote', quote,
                            'source_chunk_id', source_chunk_id,
                            'start_offset', start_offset,
                            'end_offset', end_offset,
                            'confidence', confidence
                        ) ORDER BY source_index, quote
                    ),
                    '[]'::jsonb
                )
                FROM knowledge_entry_source_refs
                WHERE entry_id = $1
                """,
                ensure_uuid(target_entry_id),
            )

            if (
                str(before["status"]) == KnowledgeEntryStatus.PUBLISHED.value
                and str(before["visibility"]) == KnowledgeEntryVisibility.RUNTIME.value
                and json_list_from_db(source_refs_payload)
            ):
                await upsert_retrieval_surface_from_payload(
                    conn,
                    project_id=project_id,
                    document_id=document_id,
                    entry_id=target_entry_id,
                    stable_key=str(before["stable_key"]),
                    entry_kind=str(before["entry_kind"]),
                    title=str(before["title"]),
                    answer=str(before["answer"]),
                    embedding_text=embedding_text,
                    embedding_text_version=embedding_text_version,
                    embedding=embedding_result.embeddings[0],
                    search_text=search_text,
                    enrichment_payload_value=json_object_from_db(before["enrichment"]),
                    source_refs_payload_value=[
                        {str(key): value for key, value in item.items()}
                        for item in json_list_from_db(source_refs_payload)
                        if isinstance(item, Mapping)
                    ],
                    metadata=json_object_from_db(before["metadata"]),
                    status=KnowledgeEntryStatus.PUBLISHED.value,
                    visibility=KnowledgeEntryVisibility.RUNTIME.value,
                )
            else:
                await delete_retrieval_surface(conn, entry_id=target_entry_id)

            after = await _fetch_entry_by_id(conn, entry_id=target_entry_id)
            if after is None:
                raise RuntimeError(
                    "target knowledge entry disappeared after embedding rebuild"
                )

            await write_version_snapshot(
                conn,
                entry_id=target_entry_id,
                project_id=project_id,
                document_id=document_id,
                action_id=action_id,
                before=before,
                after=after,
                from_version=entry_version,
                to_version=entry_version,
            )


async def update_entry_status_visibility(
    pool: asyncpg.Pool,
    *,
    create_action: ManualCurationActionCreator,
    project_id: str,
    document_id: str,
    entry_id: str,
    action_type: str,
    actor_user_id: str,
    expected_version: int | None,
    status: str,
    visibility: str,
    reason: str,
    idempotency_key: str,
) -> EntryMutationResult:
    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await _fetch_entry_for_update(
                conn,
                project_id=project_id,
                document_id=document_id,
                entry_id=entry_id,
            )
            if before is None:
                raise NotFoundError("knowledge entry not found")

            if (
                expected_version is not None
                and int(before["version"]) != expected_version
            ):
                raise ConflictError("version_conflict")

            if status == KnowledgeEntryStatus.PUBLISHED.value:
                source_ref_count = await conn.fetchval(
                    "SELECT count(*) FROM knowledge_entry_source_refs WHERE entry_id = $1",
                    ensure_uuid(entry_id),
                )
                if int(source_ref_count or 0) == 0:
                    raise ConflictError("source_refs_required_to_publish")

            action_id = await create_action(
                conn,
                project_id=project_id,
                document_id=document_id,
                action_type=action_type,
                actor_user_id=actor_user_id,
                target_entry_id=entry_id,
                target_entry_ids=(entry_id,),
                reason=reason,
                payload={
                    "entry_id": entry_id,
                    "status": status,
                    "visibility": visibility,
                    "expected_version": expected_version,
                },
                idempotency_key=idempotency_key,
                source_kind="manual_status_change",
            )

            previous_version = int(before["version"])
            next_version = previous_version + 1
            metadata = json_object_from_db(before["metadata"])
            curation = metadata.get("curation")
            curation_payload = dict(curation) if isinstance(curation, Mapping) else {}
            curation_payload["last_status_action"] = {
                "action_type": action_type,
                "reason": reason,
                "actor_user_id": actor_user_id,
            }
            metadata["curation"] = curation_payload

            await conn.execute(
                """
                UPDATE knowledge_entries
                SET status = $2,
                    visibility = $3,
                    version = $4,
                    metadata = $5::jsonb,
                    updated_at = now()
                WHERE id = $1
                """,
                ensure_uuid(entry_id),
                status,
                visibility,
                next_version,
                json.dumps(metadata, ensure_ascii=False, default=str),
            )

            await delete_retrieval_surface(conn, entry_id=entry_id)

            after = await _fetch_entry_by_id(conn, entry_id=entry_id)
            if after is None:
                raise RuntimeError("knowledge entry disappeared after status update")

            await write_version_snapshot(
                conn,
                entry_id=entry_id,
                project_id=project_id,
                document_id=document_id,
                action_id=action_id,
                before=before,
                after=after,
                from_version=previous_version,
                to_version=next_version,
            )
            await mark_action_applied_raw(conn, action_id)

    return EntryMutationResult(action_id=action_id, entry_id=entry_id)


async def update_entry_content(
    pool: asyncpg.Pool,
    *,
    create_action: ManualCurationActionCreator,
    project_id: str,
    document_id: str,
    entry_id: str,
    actor_user_id: str,
    patch: KnowledgeEntryPatch,
) -> EntryMutationResult:
    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await _fetch_entry_for_update(
                conn,
                project_id=project_id,
                document_id=document_id,
                entry_id=entry_id,
            )
            if before is None:
                raise NotFoundError("knowledge entry not found")

            if (
                patch.expected_version is not None
                and int(before["version"]) != patch.expected_version
            ):
                raise ConflictError("version_conflict")

            title = " ".join(
                (patch.title if patch.title is not None else str(before["title"]))
                .strip()
                .split()
            )
            answer = " ".join(
                (patch.answer if patch.answer is not None else str(before["answer"]))
                .strip()
                .split()
            )

            enrichment = dict(json_object_from_db(before["enrichment"]))
            if patch.enrichment is not None:
                enrichment.update(json_object_from_unknown(dict(patch.enrichment)))

            metadata = json_object_from_db(before["metadata"])
            curation = metadata.get("curation")
            curation_payload = dict(curation) if isinstance(curation, Mapping) else {}
            curation_payload["last_manual_edit"] = {
                "reason": patch.reason,
                "actor_user_id": actor_user_id,
            }
            metadata["curation"] = curation_payload

            action_type = "edit_entry_enrichment"
            if patch.answer is not None:
                action_type = "edit_entry_answer"
            if patch.title is not None:
                action_type = "edit_entry_title"

            action_id = await create_action(
                conn,
                project_id=project_id,
                document_id=document_id,
                action_type=action_type,
                actor_user_id=actor_user_id,
                target_entry_id=entry_id,
                target_entry_ids=(entry_id,),
                reason=patch.reason,
                payload={
                    "entry_id": entry_id,
                    "patch": {
                        "title": patch.title,
                        "answer": patch.answer,
                        "enrichment": patch.enrichment,
                    },
                    "expected_version": patch.expected_version,
                },
                idempotency_key=patch.idempotency_key,
                source_kind="manual_entry_edit",
            )

            previous_version = int(before["version"])
            next_version = previous_version + 1

            await conn.execute(
                """
                UPDATE knowledge_entries
                SET title = $2,
                    answer = $3,
                    enrichment = $4::jsonb,
                    metadata = $5::jsonb,
                    version = $6,
                    updated_at = now()
                WHERE id = $1
                """,
                ensure_uuid(entry_id),
                title,
                answer,
                json.dumps(enrichment, ensure_ascii=False, default=str),
                json.dumps(metadata, ensure_ascii=False, default=str),
                next_version,
            )

            await update_retrieval_surface_content(
                conn,
                entry_id=entry_id,
                title=title,
                answer=answer,
                enrichment=enrichment,
                metadata=metadata,
            )

            after = await _fetch_entry_by_id(conn, entry_id=entry_id)
            if after is None:
                raise RuntimeError("knowledge entry disappeared after content update")

            await write_version_snapshot(
                conn,
                entry_id=entry_id,
                project_id=project_id,
                document_id=document_id,
                action_id=action_id,
                before=before,
                after=after,
                from_version=previous_version,
                to_version=next_version,
            )
            await mark_action_applied_raw(conn, action_id)

    return EntryMutationResult(action_id=action_id, entry_id=entry_id)


async def restore_entry_version(
    pool: asyncpg.Pool,
    *,
    create_action: ManualCurationActionCreator,
    project_id: str,
    document_id: str,
    entry_id: str,
    version_id: str,
    actor_user_id: str,
    reason: str,
) -> EntryMutationResult:
    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await _fetch_entry_for_update(
                conn,
                project_id=project_id,
                document_id=document_id,
                entry_id=entry_id,
            )
            version = await conn.fetchrow(
                """
                SELECT id, new_snapshot
                FROM knowledge_entry_versions
                WHERE id = $1
                  AND project_id = $2
                  AND document_id = $3
                  AND entry_id = $4
                """,
                ensure_uuid(version_id),
                ensure_uuid(project_id),
                ensure_uuid(document_id),
                ensure_uuid(entry_id),
            )
            if before is None or version is None:
                raise NotFoundError("entry version not found")

            snapshot = json_object_from_db(version["new_snapshot"])
            action_id = await create_action(
                conn,
                project_id=project_id,
                document_id=document_id,
                action_type="restore_entry",
                actor_user_id=actor_user_id,
                target_entry_id=entry_id,
                target_entry_ids=(entry_id,),
                reason=reason,
                payload={"entry_id": entry_id, "version_id": version_id},
                idempotency_key=f"restore:{version_id}:{int(before['version'])}",
                source_kind="manual_curation",
            )

            next_version = int(before["version"]) + 1
            await conn.execute(
                """
                UPDATE knowledge_entries
                SET title = $2,
                    answer = $3,
                    status = $4,
                    visibility = $5,
                    enrichment = $6::jsonb,
                    metadata = $7::jsonb,
                    version = $8,
                    updated_at = now()
                WHERE id = $1
                """,
                ensure_uuid(entry_id),
                str(snapshot.get("title") or before["title"]),
                str(snapshot.get("answer") or before["answer"]),
                str(snapshot.get("status") or before["status"]),
                str(snapshot.get("visibility") or before["visibility"]),
                json.dumps(
                    snapshot.get("enrichment")
                    if isinstance(snapshot.get("enrichment"), Mapping)
                    else {},
                    ensure_ascii=False,
                    default=str,
                ),
                json.dumps(
                    snapshot.get("metadata")
                    if isinstance(snapshot.get("metadata"), Mapping)
                    else {},
                    ensure_ascii=False,
                    default=str,
                ),
                next_version,
            )

            await delete_retrieval_surface(conn, entry_id=entry_id)

            after = await _fetch_entry_by_id(conn, entry_id=entry_id)
            if after is None:
                raise RuntimeError("knowledge entry disappeared after version restore")

            await write_version_snapshot(
                conn,
                entry_id=entry_id,
                project_id=project_id,
                document_id=document_id,
                action_id=action_id,
                before=before,
                after=after,
                from_version=int(before["version"]),
                to_version=next_version,
            )
            await mark_action_applied_raw(conn, action_id)

    return EntryMutationResult(action_id=action_id, entry_id=entry_id)


async def apply_manual_entry_merge(
    pool: asyncpg.Pool,
    *,
    create_action: ManualCurationActionCreator,
    load_existing_action: ManualCurationActionLoader,
    project_id: str,
    document_id: str,
    actor_user_id: str,
    request: KnowledgeEntryMergeRequest,
    preview: KnowledgeEntryMergePreview,
    merge_action_payload: Mapping[str, object],
) -> ManualEntryMergeMutationResult:
    async with pool.acquire() as conn:
        async with conn.transaction():
            selected_ids = (
                request.parent_entry_id,
                *request.absorbed_entry_ids,
            )
            if len(selected_ids) < 2 or len(selected_ids) > 12:
                raise ValidationError("merge selection must contain 2..12 entries")
            if len(set(selected_ids)) != len(selected_ids):
                raise ValidationError("duplicate_merge_entry_ids")
            if request.parent_entry_id in request.absorbed_entry_ids:
                raise ValidationError("parent_entry_id cannot be absorbed")

            existing_action = await load_existing_action(
                conn,
                project_id=project_id,
                document_id=document_id,
                source_kind="manual_merge",
                idempotency_key=request.idempotency_key,
                payload=merge_action_payload,
            )
            if existing_action is not None:
                result_payload = existing_action["result_payload"]
                if not isinstance(result_payload, Mapping) or not result_payload:
                    raise ConflictError("idempotency_replay_missing_result")
                return ManualEntryMergeMutationResult(
                    action_id=str(existing_action["action_id"]),
                    parent_version=preview.parent_entry_before.version,
                    replay_payload={
                        str(key): value for key, value in result_payload.items()
                    },
                )

            rows = await conn.fetch(
                """
                SELECT id, project_id, document_id, compiler_run_id, stable_key, entry_kind,
                       title, answer, status, visibility, version, compiler_version,
                       embedding_text, embedding_text_version, enrichment, metadata
                FROM knowledge_entries
                WHERE project_id = $1
                  AND document_id = $2
                  AND id = ANY($3::uuid[])
                FOR UPDATE
                """,
                ensure_uuid(project_id),
                ensure_uuid(document_id),
                [ensure_uuid(item) for item in selected_ids],
            )
            if len(rows) != len(selected_ids):
                raise NotFoundError("merge entries not found in document")

            by_id = {str(row["id"]): row for row in rows}
            parent_row = by_id[request.parent_entry_id]

            parent_status = str(parent_row["status"])
            if parent_status in {
                KnowledgeEntryStatus.REJECTED.value,
                KnowledgeEntryStatus.ARCHIVED.value,
                KnowledgeEntryStatus.MERGED.value,
            }:
                raise ConflictError(f"invalid_parent_status:{parent_status}")

            if (
                request.parent_expected_version is not None
                and int(parent_row["version"]) != request.parent_expected_version
            ):
                raise ConflictError("parent_version_conflict")

            for absorbed_id in request.absorbed_entry_ids:
                absorbed_row = by_id.get(absorbed_id)
                if absorbed_row is None:
                    raise NotFoundError("absorbed entry not found")

                expected_absorbed_version = request.absorbed_expected_versions.get(
                    absorbed_id
                )
                if (
                    expected_absorbed_version is not None
                    and int(absorbed_row["version"]) != expected_absorbed_version
                ):
                    raise ConflictError(f"absorbed_version_conflict:{absorbed_id}")

                absorbed_metadata = json_object_from_db(absorbed_row["metadata"])
                absorbed_curation = absorbed_metadata.get("curation")
                absorbed_curation_payload = (
                    dict(absorbed_curation)
                    if isinstance(absorbed_curation, Mapping)
                    else {}
                )
                if absorbed_curation_payload.get("merged_into"):
                    raise ConflictError(f"absorbed_already_merged:{absorbed_id}")

            action_id = await create_action(
                conn,
                project_id=project_id,
                document_id=document_id,
                action_type="merge_entries",
                actor_user_id=actor_user_id,
                target_entry_id=request.parent_entry_id,
                target_entry_ids=selected_ids,
                reason=request.merge_instruction,
                payload=merge_action_payload,
                idempotency_key=request.idempotency_key,
                source_kind="manual_merge",
            )

            proposed = preview.proposed_entry_after
            raw_metadata = proposed.get("metadata")
            raw_enrichment = proposed.get("enrichment")
            raw_source_refs = proposed.get("source_refs")
            metadata: Mapping[str, object] = (
                raw_metadata if isinstance(raw_metadata, Mapping) else {}
            )
            enrichment: Mapping[str, object] = (
                raw_enrichment if isinstance(raw_enrichment, Mapping) else {}
            )
            source_refs: Sequence[object] = (
                raw_source_refs
                if isinstance(raw_source_refs, Sequence)
                and not isinstance(raw_source_refs, str | bytes | bytearray)
                else ()
            )

            if (
                str(parent_row["status"]) == KnowledgeEntryStatus.PUBLISHED.value
                and str(parent_row["visibility"])
                == KnowledgeEntryVisibility.RUNTIME.value
                and not source_refs
            ):
                raise ConflictError("source_refs_required_for_published_parent")

            previous_version = int(parent_row["version"])
            parent_version = previous_version + 1

            await conn.execute(
                """
                UPDATE knowledge_entries
                SET title = $2,
                    answer = $3,
                    enrichment = $4::jsonb,
                    metadata = $5::jsonb,
                    version = $6,
                    updated_at = now()
                WHERE id = $1
                """,
                ensure_uuid(request.parent_entry_id),
                str(proposed["title"]),
                str(proposed["answer"]),
                json.dumps(
                    json_object_from_unknown(dict(enrichment)),
                    ensure_ascii=False,
                    default=str,
                ),
                json.dumps(
                    json_object_from_unknown(dict(metadata)),
                    ensure_ascii=False,
                    default=str,
                ),
                parent_version,
            )

            await replace_entry_source_refs_from_payload(
                conn,
                entry_id=request.parent_entry_id,
                source_refs=source_refs,
            )

            parent_after = await _fetch_entry_by_id(
                conn,
                entry_id=request.parent_entry_id,
            )
            if parent_after is None:
                raise RuntimeError("parent entry disappeared after merge")

            await write_version_snapshot(
                conn,
                entry_id=request.parent_entry_id,
                project_id=project_id,
                document_id=document_id,
                action_id=action_id,
                before=parent_row,
                after=parent_after,
                from_version=previous_version,
                to_version=parent_version,
            )

            for absorbed_id in request.absorbed_entry_ids:
                before = by_id[absorbed_id]
                metadata_before = json_object_from_db(before["metadata"])
                curation = metadata_before.get("curation")
                curation_payload = (
                    dict(curation) if isinstance(curation, Mapping) else {}
                )
                curation_payload["merged_into"] = request.parent_entry_id
                curation_payload["absorbed_by_action_id"] = action_id
                metadata_before["curation"] = curation_payload
                absorbed_next_version = int(before["version"]) + 1

                await conn.execute(
                    """
                    UPDATE knowledge_entries
                    SET status = 'merged',
                        visibility = 'hidden',
                        metadata = $2::jsonb,
                        version = $3,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    ensure_uuid(absorbed_id),
                    json.dumps(metadata_before, ensure_ascii=False, default=str),
                    absorbed_next_version,
                )

                await delete_retrieval_surface(conn, entry_id=absorbed_id)

                after = await _fetch_entry_by_id(conn, entry_id=absorbed_id)
                if after is not None:
                    await write_version_snapshot(
                        conn,
                        entry_id=absorbed_id,
                        project_id=project_id,
                        document_id=document_id,
                        action_id=action_id,
                        before=before,
                        after=after,
                        from_version=int(before["version"]),
                        to_version=absorbed_next_version,
                    )

            await delete_retrieval_surface(conn, entry_id=request.parent_entry_id)
            await mark_action_in_progress_raw(conn, action_id)

    return ManualEntryMergeMutationResult(
        action_id=action_id,
        parent_version=parent_version,
    )

"""Persistence helpers for canonical knowledge entries and retrieval surface rows."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

import asyncpg

from src.domain.project_plane.embedding_text import (
    build_canonical_entry_embedding_text,
    build_retrieval_surface_search_text,
)
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    SourceRef,
)
from src.infrastructure.db.repositories.knowledge_compiler_payloads import (
    compiler_jsonb_array_payload,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import (
    jsonb_object_payload,
    pg_vector_text,
    source_ref_payload,
)
from src.utils.uuid_utils import ensure_uuid


def batched_canonical_entries(
    entries: Sequence[CanonicalKnowledgeEntry], batch_size: int
) -> Iterator[Sequence[CanonicalKnowledgeEntry]]:
    for start in range(0, len(entries), batch_size):
        yield entries[start : start + batch_size]


def entry_embedding_text(entry: CanonicalKnowledgeEntry) -> str:
    return build_canonical_entry_embedding_text(entry).value


def entry_embedding_text_version(entry: CanonicalKnowledgeEntry) -> str:
    return build_canonical_entry_embedding_text(entry).version


def enrichment_payload(entry: CanonicalKnowledgeEntry) -> dict[str, object]:
    return {
        "questions": list(entry.enrichment.questions),
        "paraphrases": list(entry.enrichment.paraphrases),
        "synonyms": list(entry.enrichment.synonyms),
        "typo_queries": list(entry.enrichment.typo_queries),
        "colloquial_queries": list(entry.enrichment.colloquial_queries),
        "tags": list(entry.enrichment.tags),
        "retrieval_guards": list(entry.enrichment.retrieval_guards),
    }


def surface_search_text(entry: CanonicalKnowledgeEntry) -> str:
    return build_retrieval_surface_search_text(entry)


def source_refs_payload_from_refs(
    source_refs: Sequence[SourceRef],
) -> list[dict[str, object]]:
    return [source_ref_payload(source_ref) for source_ref in source_refs]


async def delete_retrieval_surface(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
) -> None:
    await conn.execute(
        "DELETE FROM knowledge_retrieval_surface WHERE entry_id = $1",
        ensure_uuid(entry_id),
    )


async def update_retrieval_surface_metadata(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
    enrichment: Mapping[str, object],
    metadata: Mapping[str, object],
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_retrieval_surface
        SET enrichment = $2::jsonb,
            metadata = $3::jsonb,
            updated_at = now()
        WHERE entry_id = $1
        """,
        ensure_uuid(entry_id),
        jsonb_object_payload(enrichment),
        jsonb_object_payload(metadata),
    )


async def update_retrieval_surface_content(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
    title: str,
    answer: str,
    enrichment: Mapping[str, object],
    metadata: Mapping[str, object],
) -> None:
    await conn.execute(
        """
        UPDATE knowledge_retrieval_surface
        SET title = $2,
            answer = $3,
            enrichment = $4::jsonb,
            metadata = $5::jsonb,
            updated_at = now()
        WHERE entry_id = $1
        """,
        ensure_uuid(entry_id),
        title,
        answer,
        jsonb_object_payload(enrichment),
        jsonb_object_payload(metadata),
    )


async def delete_document_retrieval_surface(
    conn: asyncpg.Connection,
    *,
    document_id: str,
) -> None:
    await conn.execute(
        "DELETE FROM knowledge_retrieval_surface WHERE document_id = $1",
        ensure_uuid(document_id),
    )


async def replace_entry_source_refs(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
    source_refs: Sequence[SourceRef],
) -> list[dict[str, object]]:
    entry_uuid = ensure_uuid(entry_id)
    payload = source_refs_payload_from_refs(source_refs)

    await conn.execute(
        "DELETE FROM knowledge_entry_source_refs WHERE entry_id = $1",
        entry_uuid,
    )

    for source_ref in source_refs:
        if source_ref.source_chunk_id is None:
            continue
        await conn.execute(
            """
            INSERT INTO knowledge_entry_source_refs (
                entry_id,
                source_chunk_id,
                source_index,
                quote,
                quote_hash,
                start_offset,
                end_offset,
                confidence,
                metadata
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                md5(coalesce($4, '')),
                $5,
                $6,
                $7,
                '{}'::jsonb
            )
            ON CONFLICT DO NOTHING
            """,
            entry_uuid,
            source_ref.source_chunk_id,
            source_ref.source_index or 0,
            source_ref.quote,
            source_ref.start_offset,
            source_ref.end_offset,
            source_ref.confidence,
        )

    return payload


async def replace_entry_source_refs_from_payload(
    conn: asyncpg.Connection,
    *,
    entry_id: str,
    source_refs: Sequence[object],
) -> list[dict[str, object]]:
    await conn.execute(
        "DELETE FROM knowledge_entry_source_refs WHERE entry_id = $1",
        ensure_uuid(entry_id),
    )

    inserted_payload: list[dict[str, object]] = []
    for ref in source_refs:
        if not isinstance(ref, Mapping) or not ref.get("source_chunk_id"):
            continue

        source_chunk_id = str(ref["source_chunk_id"])
        source_index = int(ref.get("source_index") or 0)
        quote = str(ref.get("quote") or "")
        start_offset = ref.get("start_offset")
        end_offset = ref.get("end_offset")
        confidence = ref.get("confidence")

        await conn.execute(
            """
            INSERT INTO knowledge_entry_source_refs (
                entry_id,
                source_chunk_id,
                source_index,
                quote,
                quote_hash,
                start_offset,
                end_offset,
                confidence,
                metadata
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                md5(coalesce($4, '')),
                $5,
                $6,
                $7,
                '{}'::jsonb
            )
            ON CONFLICT DO NOTHING
            """,
            ensure_uuid(entry_id),
            source_chunk_id,
            source_index,
            quote,
            start_offset,
            end_offset,
            confidence,
        )
        inserted_payload.append(
            {
                "source_chunk_id": source_chunk_id,
                "source_index": source_index,
                "quote": quote,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "confidence": confidence,
            }
        )

    return inserted_payload


async def upsert_retrieval_surface(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    entry: CanonicalKnowledgeEntry,
    embedding: Sequence[float],
    enrichment_payload_value: Mapping[str, object],
    source_refs_payload_value: Sequence[Mapping[str, object]],
    metadata: Mapping[str, object],
    status: str,
    visibility: str,
) -> None:
    embedding_text = entry_embedding_text(entry)
    embedding_text_version = entry_embedding_text_version(entry)

    await conn.execute(
        """
        INSERT INTO knowledge_retrieval_surface (
            project_id,
            document_id,
            entry_id,
            stable_key,
            entry_kind,
            title,
            answer,
            embedding_text,
            embedding_text_version,
            embedding,
            search_text,
            enrichment,
            source_refs,
            metadata,
            status,
            visibility
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
            $10::vector,
            $11,
            $12::jsonb,
            $13::jsonb,
            $14::jsonb,
            $15,
            $16
        )
        ON CONFLICT (entry_id)
        DO UPDATE SET
            stable_key = EXCLUDED.stable_key,
            entry_kind = EXCLUDED.entry_kind,
            title = EXCLUDED.title,
            answer = EXCLUDED.answer,
            embedding_text = EXCLUDED.embedding_text,
            embedding_text_version = EXCLUDED.embedding_text_version,
            embedding = EXCLUDED.embedding,
            search_text = EXCLUDED.search_text,
            enrichment = EXCLUDED.enrichment,
            source_refs = EXCLUDED.source_refs,
            metadata = EXCLUDED.metadata,
            status = EXCLUDED.status,
            visibility = EXCLUDED.visibility,
            updated_at = now()
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        ensure_uuid(entry.id),
        entry.stable_key,
        entry.entry_kind.value,
        entry.title,
        entry.answer,
        embedding_text,
        embedding_text_version,
        pg_vector_text(list(embedding)),
        surface_search_text(entry),
        jsonb_object_payload(enrichment_payload_value),
        compiler_jsonb_array_payload(source_refs_payload_value),
        jsonb_object_payload(metadata),
        status,
        visibility,
    )


async def upsert_retrieval_surface_from_payload(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    entry_id: str,
    stable_key: str,
    entry_kind: str,
    title: str,
    answer: str,
    embedding_text: str,
    embedding_text_version: str,
    embedding: list[float],
    search_text: str,
    enrichment_payload_value: Mapping[str, object],
    source_refs_payload_value: Sequence[Mapping[str, object]],
    metadata: Mapping[str, object],
    status: str,
    visibility: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO knowledge_retrieval_surface (
            project_id,
            document_id,
            entry_id,
            stable_key,
            entry_kind,
            title,
            answer,
            embedding_text,
            embedding_text_version,
            embedding,
            search_text,
            enrichment,
            source_refs,
            metadata,
            status,
            visibility
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
            $10::vector,
            $11,
            $12::jsonb,
            $13::jsonb,
            $14::jsonb,
            $15,
            $16
        )
        ON CONFLICT (entry_id)
        DO UPDATE SET
            stable_key = EXCLUDED.stable_key,
            entry_kind = EXCLUDED.entry_kind,
            title = EXCLUDED.title,
            answer = EXCLUDED.answer,
            embedding_text = EXCLUDED.embedding_text,
            embedding_text_version = EXCLUDED.embedding_text_version,
            embedding = EXCLUDED.embedding,
            search_text = EXCLUDED.search_text,
            enrichment = EXCLUDED.enrichment,
            source_refs = EXCLUDED.source_refs,
            metadata = EXCLUDED.metadata,
            status = EXCLUDED.status,
            visibility = EXCLUDED.visibility,
            updated_at = now()
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
        ensure_uuid(entry_id),
        stable_key,
        entry_kind,
        title,
        answer,
        embedding_text,
        embedding_text_version,
        pg_vector_text(embedding),
        search_text,
        jsonb_object_payload(enrichment_payload_value),
        compiler_jsonb_array_payload(source_refs_payload_value),
        jsonb_object_payload(metadata),
        status,
        visibility,
    )


async def sync_entry_retrieval_surface(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    entry: CanonicalKnowledgeEntry,
    embedding: Sequence[float],
    enrichment_payload_value: Mapping[str, object],
    source_refs_payload_value: Sequence[Mapping[str, object]],
    metadata: Mapping[str, object],
    status: str,
    visibility: str,
) -> None:
    await delete_retrieval_surface(conn, entry_id=entry.id)

    if not entry.is_published_runtime_entry:
        return

    await upsert_retrieval_surface(
        conn,
        project_id=project_id,
        document_id=document_id,
        entry=entry,
        embedding=embedding,
        enrichment_payload_value=enrichment_payload_value,
        source_refs_payload_value=source_refs_payload_value,
        metadata=metadata,
        status=status,
        visibility=visibility,
    )

from __future__ import annotations

from collections.abc import Sequence

import asyncpg

from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.infrastructure.db.repositories.knowledge_db_codecs import (
    json_object_from_db,
    jsonb_object_payload,
)
from src.utils.uuid_utils import ensure_uuid


async def list_document_source_chunks(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
) -> tuple[SourceChunk, ...]:
    rows = await conn.fetch(
        """
        SELECT
            id,
            project_id,
            document_id,
            source_index,
            content,
            page,
            section_title,
            start_offset,
            end_offset,
            checksum,
            metadata,
            created_at
        FROM knowledge_source_chunks
        WHERE project_id = $1
          AND document_id = $2
        ORDER BY source_index ASC
        """,
        ensure_uuid(project_id),
        ensure_uuid(document_id),
    )

    return tuple(
        SourceChunk(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            document_id=str(row["document_id"]),
            source_index=int(row["source_index"]),
            content=str(row["content"]),
            page=int(row["page"]) if row["page"] is not None else None,
            section_title=str(row["section_title"] or ""),
            start_offset=int(row["start_offset"])
            if row["start_offset"] is not None
            else None,
            end_offset=int(row["end_offset"])
            if row["end_offset"] is not None
            else None,
            checksum=str(row["checksum"] or ""),
            metadata=json_object_from_db(row["metadata"]),
            created_at=row["created_at"],
        )
        for row in rows
    )


async def delete_document_source_chunks(
    conn: asyncpg.Connection,
    *,
    document_id: str,
) -> None:
    await conn.execute(
        "DELETE FROM knowledge_source_chunks WHERE document_id = $1",
        ensure_uuid(document_id),
    )


async def replace_document_source_chunks(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    document_id: str,
    chunks: Sequence[SourceChunk],
) -> int:
    await delete_document_source_chunks(conn, document_id=document_id)

    for chunk in chunks:
        await conn.execute(
            """
            INSERT INTO knowledge_source_chunks (
                id,
                project_id,
                document_id,
                source_index,
                content,
                page,
                section_title,
                start_offset,
                end_offset,
                checksum,
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
                $10,
                $11::jsonb
            )
            ON CONFLICT (id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                document_id = EXCLUDED.document_id,
                source_index = EXCLUDED.source_index,
                content = EXCLUDED.content,
                page = EXCLUDED.page,
                section_title = EXCLUDED.section_title,
                start_offset = EXCLUDED.start_offset,
                end_offset = EXCLUDED.end_offset,
                checksum = EXCLUDED.checksum,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            chunk.id,
            ensure_uuid(project_id),
            ensure_uuid(document_id),
            chunk.source_index,
            chunk.content,
            chunk.page,
            chunk.section_title,
            chunk.start_offset,
            chunk.end_offset,
            chunk.checksum or None,
            jsonb_object_payload(chunk.metadata),
        )

    return len(chunks)

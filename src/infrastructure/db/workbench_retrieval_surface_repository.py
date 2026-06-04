from __future__ import annotations

import json
from collections.abc import Awaitable, Mapping, Sequence
from typing import Protocol
from uuid import UUID, uuid5

from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    WorkbenchRetrievalSurfaceEntry,
)
from src.infrastructure.db.repositories.knowledge_db_codecs import pg_vector_text
from src.utils.uuid_utils import ensure_uuid


_WORKBENCH_RETRIEVAL_NAMESPACE = UUID("0d7b8e74-6867-4b45-9c1b-88e1fefb60cf")


class WorkbenchRetrievalSurfaceTransaction(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> object: ...


class WorkbenchRetrievalSurfaceConnection(Protocol):
    def execute(self, query: str, *args: object) -> Awaitable[str]: ...

    def fetchval(self, query: str, *args: object) -> Awaitable[object]: ...

    def transaction(self) -> WorkbenchRetrievalSurfaceTransaction: ...


class WorkbenchRetrievalSurfaceRepository:
    def __init__(self, connection: WorkbenchRetrievalSurfaceConnection) -> None:
        self._connection = connection

    async def replace_workbench_fact_runtime_surface_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        entries: tuple[WorkbenchRetrievalSurfaceEntry, ...],
    ) -> int:
        project_uuid = ensure_uuid(project_id)

        async with self._connection.transaction():
            await self._connection.execute(
                """
                DELETE FROM knowledge_retrieval_surface
                WHERE project_id = $1
                  AND entry_kind = 'faq_workbench_fact'
                  AND metadata ->> 'workbench_document_id' = $2
                """,
                project_uuid,
                document_id,
            )

            await self._connection.execute(
                """
                DELETE FROM knowledge_entries
                WHERE project_id = $1
                  AND entry_kind = 'faq_workbench_fact'
                  AND metadata ->> 'workbench_document_id' = $2
                """,
                project_uuid,
                document_id,
            )

            for entry in entries:
                entry_uuid = _entry_uuid(entry)
                stable_key = _stable_key(entry)
                enrichment = _json(entry.enrichment)
                source_refs = _json(list(entry.source_refs))
                metadata = _json(
                    {
                        "contract": "faq_workbench_fact_runtime_projection",
                        "workbench_document_id": document_id,
                        "workbench_fact_id": entry.fact_id,
                        "workbench_entry_id": entry.entry_id,
                    }
                )

                await self._connection.execute(
                    """
                    INSERT INTO knowledge_entries (
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
                    )
                    VALUES (
                        $1,
                        $2,
                        NULL,
                        $3,
                        $4,
                        'faq_workbench_fact',
                        $5,
                        $6,
                        'published',
                        'runtime',
                        1,
                        'faq_workbench_runtime_projection_v1',
                        $7,
                        'faq_workbench_runtime_projection_v1',
                        $8::jsonb,
                        $9::jsonb
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        stable_key = EXCLUDED.stable_key,
                        title = EXCLUDED.title,
                        answer = EXCLUDED.answer,
                        status = EXCLUDED.status,
                        visibility = EXCLUDED.visibility,
                        embedding_text = EXCLUDED.embedding_text,
                        embedding_text_version = EXCLUDED.embedding_text_version,
                        enrichment = EXCLUDED.enrichment,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """,
                    entry_uuid,
                    project_uuid,
                    document_id,
                    stable_key,
                    entry.title,
                    entry.answer,
                    entry.embedding_text,
                    enrichment,
                    metadata,
                )

                await self._connection.execute(
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
                        NULL,
                        $2,
                        $3,
                        'faq_workbench_fact',
                        $4,
                        $5,
                        $6,
                        'faq_workbench_runtime_projection_v1',
                        $7::vector,
                        $8,
                        $9::jsonb,
                        $10::jsonb,
                        $11::jsonb,
                        'published',
                        'runtime'
                    )
                    ON CONFLICT (entry_id) DO UPDATE SET
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
                    project_uuid,
                    entry_uuid,
                    stable_key,
                    entry.title,
                    entry.answer,
                    entry.embedding_text,
                    pg_vector_text(entry.embedding),
                    entry.search_text,
                    enrichment,
                    source_refs,
                    metadata,
                )

        return len(entries)


def _entry_uuid(entry: WorkbenchRetrievalSurfaceEntry) -> UUID:
    return uuid5(
        _WORKBENCH_RETRIEVAL_NAMESPACE,
        f"{entry.project_id}:{entry.document_id}:{entry.fact_id}",
    )


def _stable_key(entry: WorkbenchRetrievalSurfaceEntry) -> str:
    return f"workbench:{entry.document_id}:{entry.fact_id}"


def _json(value: Mapping[str, object] | Sequence[object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "WorkbenchRetrievalSurfaceConnection",
    "WorkbenchRetrievalSurfaceRepository",
]

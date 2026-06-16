from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)


class AsyncSourceManagementConnectionLike(Protocol):
    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...
    async def execute(self, query: str, *args: object) -> object: ...


class PostgresSourceManagementRepository(SourceManagementRepositoryPort):
    def __init__(self, connection: AsyncSourceManagementConnectionLike) -> None:
        self._connection = connection

    async def save_source_document(self, document: SourceDocument) -> None:
        await self._connection.execute(
            "INSERT INTO source_documents (document_ref, project_id, source_format, content_hash, original_filename, created_at) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (document_ref) DO UPDATE SET project_id = EXCLUDED.project_id, source_format = EXCLUDED.source_format, content_hash = EXCLUDED.content_hash, original_filename = EXCLUDED.original_filename, created_at = EXCLUDED.created_at",
            document.document_ref.value,
            document.project_id,
            document.source_format.value,
            document.content_hash,
            document.original_filename,
            document.created_at,
        )

        # Bridge the new source-ingestion vertical into the Workbench document
        # read model used by the document list, progress, and workflow live-state
        # endpoints. Without this row the workflow can start while the frontend
        # has no document id to poll.
        await self._connection.execute(
            """
            INSERT INTO knowledge_workbench_documents (
                document_id,
                project_id,
                file_name,
                source_type,
                content_hash,
                upload_id,
                file_size_bytes,
                status,
                current_processing_run_id,
                uploaded_by_actor_type,
                uploaded_by_actor_id,
                trusted_upload,
                retention_state,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'processing', NULL, 'source_ingestion', $8, TRUE, 'active_processing', $9, $9)
            ON CONFLICT (document_id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                file_name = EXCLUDED.file_name,
                source_type = EXCLUDED.source_type,
                content_hash = EXCLUDED.content_hash,
                upload_id = EXCLUDED.upload_id,
                file_size_bytes = EXCLUDED.file_size_bytes,
                status = CASE
                    WHEN knowledge_workbench_documents.status IN ('processed', 'published')
                    THEN knowledge_workbench_documents.status
                    ELSE EXCLUDED.status
                END,
                uploaded_by_actor_type = EXCLUDED.uploaded_by_actor_type,
                uploaded_by_actor_id = EXCLUDED.uploaded_by_actor_id,
                trusted_upload = EXCLUDED.trusted_upload,
                retention_state = EXCLUDED.retention_state,
                updated_at = EXCLUDED.updated_at,
                deleted_at = NULL
            """,
            document.document_ref.value,
            document.project_id,
            document.original_filename or document.document_ref.value,
            document.source_format.value,
            document.content_hash,
            document.document_ref.value,
            document.file_size_bytes,
            "source_ingestion",
            document.created_at,
        )

    async def load_source_document(
        self, document_ref: SourceDocumentRef
    ) -> SourceDocument | None:
        row = await self._connection.fetchrow(
            "SELECT document_ref, project_id, source_format, content_hash, original_filename, created_at FROM source_documents WHERE document_ref = $1",
            document_ref.value,
        )
        return None if row is None else _document_from_row(row)

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        if not units:
            return
        for unit in units:
            await self._connection.execute(
                "INSERT INTO source_units (unit_ref, document_ref, unit_kind, text, heading_path, lineage, ordinal, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (unit_ref) DO UPDATE SET document_ref = EXCLUDED.document_ref, unit_kind = EXCLUDED.unit_kind, text = EXCLUDED.text, heading_path = EXCLUDED.heading_path, lineage = EXCLUDED.lineage, ordinal = EXCLUDED.ordinal, created_at = EXCLUDED.created_at",
                unit.unit_ref.value,
                unit.document_ref.value,
                unit.unit_kind.value,
                unit.text.value,
                json.dumps(list(unit.heading_path.parts)),
                json.dumps(
                    {
                        "parent_refs": [
                            parent_ref.value for parent_ref in unit.lineage.parent_refs
                        ]
                    }
                ),
                unit.ordinal,
                unit.created_at,
            )

    async def list_source_units_for_document(
        self, document_ref: SourceDocumentRef
    ) -> tuple[SourceUnit, ...]:
        rows = await self._connection.fetch(
            "SELECT unit_ref, document_ref, unit_kind, text, heading_path, lineage, ordinal, created_at FROM source_units WHERE document_ref = $1 ORDER BY ordinal ASC",
            document_ref.value,
        )
        return tuple(_unit_from_row(row) for row in rows)

    async def load_source_unit(self, unit_ref: SourceUnitRef) -> SourceUnit | None:
        row = await self._connection.fetchrow(
            "SELECT unit_ref, document_ref, unit_kind, text, heading_path, lineage, ordinal, created_at FROM source_units WHERE unit_ref = $1",
            unit_ref.value,
        )
        return None if row is None else _unit_from_row(row)


def _document_from_row(row: Mapping[str, object]) -> SourceDocument:
    return SourceDocument(
        document_ref=SourceDocumentRef(_required_str(row, "document_ref")),
        project_id=_required_str(row, "project_id"),
        source_format=SourceFormat(_required_str(row, "source_format")),
        content_hash=_required_str(row, "content_hash"),
        original_filename=_optional_str(row, "original_filename"),
        created_at=_required_datetime(row, "created_at"),
    )


def _unit_from_row(row: Mapping[str, object]) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(_required_str(row, "unit_ref")),
        document_ref=SourceDocumentRef(_required_str(row, "document_ref")),
        unit_kind=SourceUnitKind(_required_str(row, "unit_kind")),
        text=SourceUnitText(_required_str(row, "text")),
        heading_path=HeadingPath(
            tuple(_required_str_list(_value(row, "heading_path"), "heading_path"))
        ),
        lineage=SourceUnitLineage(
            tuple(
                SourceUnitRef(value) for value in _parent_refs(_value(row, "lineage"))
            )
        ),
        ordinal=_required_int(row, "ordinal"),
        created_at=_required_datetime(row, "created_at"),
    )


def _value(row: Mapping[str, object], key: str) -> object:
    try:
        return row[key]
    except KeyError as exc:
        raise KeyError(f"Missing source management row column: {key}") from exc


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = _value(row, key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = _value(row, key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or a non-empty string")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = _value(row, key)
    if not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = _value(row, key)
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _required_str_list(value: object, field_name: str) -> list[str]:
    if isinstance(value, str):
        decoded = json.loads(value)
        value = decoded
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} values must be strings")
        result.append(item)
    return result


def _parent_refs(value: object) -> list[str]:
    if isinstance(value, str):
        decoded = json.loads(value)
        value = decoded
    if not isinstance(value, Mapping):
        raise TypeError("lineage must be a mapping")
    raw_parent_refs = value.get("parent_refs", [])
    return _required_str_list(raw_parent_refs, "lineage.parent_refs")

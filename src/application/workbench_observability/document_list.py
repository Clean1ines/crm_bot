from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class WorkbenchDocumentListQueryPort(Protocol):
    async def list_workbench_documents(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentListReadService:
    query: WorkbenchDocumentListQueryPort

    async def list_documents(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        rows = await self.query.list_workbench_documents(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
        documents = [_document_payload(row) for row in rows]
        return {
            "documents": documents,
            "items": documents,
        }


def _document_payload(row: Mapping[str, object]) -> dict[str, object]:
    total_sections = _int(row.get("section_count"))
    processed_sections = _int(row.get("processed_section_count"))
    failed_sections = _int(row.get("failed_section_count"))

    return {
        "document_id": _text(row.get("document_id")),
        "project_id": _text(row.get("project_id")),
        "file_name": _text(row.get("file_name")),
        "source_type": _text(row.get("source_type")),
        "file_size_bytes": _int(row.get("file_size_bytes")),
        "status": _text(row.get("status")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "deleted_at": _iso(row.get("deleted_at")),
        "processing_run_id": _nullable_text(row.get("processing_run_id")),
        "processing_status": _nullable_text(row.get("processing_status")),
        "processing_trigger": _nullable_text(row.get("processing_trigger")),
        "resume_policy": _nullable_text(row.get("resume_policy")),
        "started_at": _iso(row.get("started_at")),
        "finished_at": _iso(row.get("finished_at")),
        "completed_at": _iso(row.get("completed_at")),
        "section_count": total_sections,
        "total_sections": total_sections,
        "processed_section_count": processed_sections,
        "failed_section_count": failed_sections,
        "pending_section_count": _int(row.get("pending_section_count")),
        "progress": {
            "total_sections": total_sections,
            "processed_sections": processed_sections,
            "failed_sections": failed_sections,
            "pending_sections": _int(row.get("pending_section_count")),
        },
        "result_metrics": {
            "canonical_fact_count": _int(row.get("canonical_fact_count")),
            "runtime_entry_count": _int(row.get("runtime_entry_count")),
            "registry_retained": _bool(row.get("registry_retained")),
            "final_registry_snapshot_id": _nullable_text(
                row.get("final_registry_snapshot_id")
            ),
        },
        "canonical_fact_count": _int(row.get("canonical_fact_count")),
        "runtime_entry_count": _int(row.get("runtime_entry_count")),
        "registry_retained": _bool(row.get("registry_retained")),
        "final_registry_snapshot_id": _nullable_text(
            row.get("final_registry_snapshot_id")
        ),
        "uploaded_by_user_id": _nullable_text(row.get("uploaded_by_user_id")),
        "uploaded_by_actor_type": _text(row.get("uploaded_by_actor_type")),
        "uploaded_by_actor_id": _nullable_text(row.get("uploaded_by_actor_id")),
        "trusted_upload": _bool(row.get("trusted_upload")),
        "last_error_kind": _nullable_text(row.get("last_error_kind")),
        "last_error_message": _nullable_text(row.get("last_error_message")),
        "last_error_at": _iso(row.get("last_error_at")),
    }


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int(value: object) -> int:
    if value is None:
        return 0
    return int(value)


def _bool(value: object) -> bool:
    if value is None:
        return False
    return bool(value)


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)

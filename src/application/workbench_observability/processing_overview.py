from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class WorkbenchProcessingOverviewQueryPort(Protocol):
    async def list_processing_overview_documents(
        self,
        *,
        project_id: str,
    ) -> Sequence[Mapping[str, object]]: ...

    async def list_processing_overview_node_runs(
        self,
        *,
        project_id: str,
    ) -> Sequence[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class WorkbenchProcessingOverviewReadService:
    query: WorkbenchProcessingOverviewQueryPort

    async def fetch_processing_overview(
        self,
        *,
        project_id: str,
    ) -> dict[str, object]:
        documents = [
            _document_payload(row)
            for row in await self.query.list_processing_overview_documents(
                project_id=project_id,
            )
        ]
        node_runs = [
            _node_run_payload(row)
            for row in await self.query.list_processing_overview_node_runs(
                project_id=project_id,
            )
        ]

        document_status_counts = Counter(
            str(document["status"]) for document in documents
        )
        processing_status_counts = Counter(
            str(document["processing_status"] or "none") for document in documents
        )
        node_status_counts = Counter(str(run["status"]) for run in node_runs)

        active_documents = [
            document
            for document in documents
            if str(document["processing_status"]) in {"running", "queued", "processing"}
            or str(document["status"]) in {"processing", "sectioned"}
        ]
        failed_documents = [
            document
            for document in documents
            if str(document["processing_status"]) in {"failed", "error"}
            or str(document["status"]) in {"failed", "error"}
        ]
        resumable_documents = [
            document
            for document in documents
            if str(document["resume_policy"]) == "explicit_user_action"
        ]

        total_sections = sum(int(document["section_count"]) for document in documents)
        processed_sections = sum(
            int(document["processed_section_count"]) for document in documents
        )
        failed_sections = sum(
            int(document["failed_section_count"]) for document in documents
        )
        pending_sections = sum(
            int(document["pending_section_count"]) for document in documents
        )

        return {
            "project_id": project_id,
            "documents": documents,
            "items": documents,
            "summary": {
                "documents_total": len(documents),
                "active_documents": len(active_documents),
                "failed_documents": len(failed_documents),
                "resumable_documents": len(resumable_documents),
                "sections_total": total_sections,
                "processed_sections": processed_sections,
                "failed_sections": failed_sections,
                "pending_sections": pending_sections,
                "node_runs_total": len(node_runs),
                "failed_node_runs": sum(
                    1
                    for run in node_runs
                    if str(run["status"]).lower() in {"failed", "error"}
                ),
            },
            "status_counts": {
                "documents": dict(sorted(document_status_counts.items())),
                "processing_runs": dict(sorted(processing_status_counts.items())),
                "node_runs": dict(sorted(node_status_counts.items())),
            },
            "active_documents": _document_refs(active_documents),
            "failed_documents": _document_refs(failed_documents),
            "resumable_documents": _document_refs(resumable_documents),
        }


def _document_payload(row: Mapping[str, object]) -> dict[str, object]:
    section_count = _int(row.get("section_count"))
    processed_count = _int(row.get("processed_section_count"))
    failed_count = _int(row.get("failed_section_count"))
    pending_count = _int(row.get("pending_section_count"))

    return {
        "document_id": _text(row.get("document_id")),
        "project_id": _text(row.get("project_id")),
        "file_name": _text(row.get("file_name")),
        "source_type": _text(row.get("source_type")),
        "file_size_bytes": _int(row.get("file_size_bytes")),
        "status": _text(row.get("status")),
        "processing_run_id": _nullable_text(row.get("processing_run_id")),
        "processing_status": _nullable_text(row.get("processing_status")),
        "processing_trigger": _nullable_text(row.get("processing_trigger")),
        "resume_policy": _nullable_text(row.get("resume_policy")),
        "section_count": section_count,
        "processed_section_count": processed_count,
        "failed_section_count": failed_count,
        "pending_section_count": pending_count,
        "progress": {
            "total_sections": section_count,
            "processed_sections": processed_count,
            "failed_sections": failed_count,
            "pending_sections": pending_count,
        },
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
        "last_error_kind": _nullable_text(row.get("last_error_kind")),
        "last_error_message": _nullable_text(row.get("last_error_message")),
        "last_error_at": _iso(row.get("last_error_at")),
    }


def _node_run_payload(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "node_run_id": _text(row.get("node_run_id")),
        "document_id": _text(row.get("document_id")),
        "processing_run_id": _text(row.get("processing_run_id")),
        "node_name": _text(row.get("node_name")),
        "status": _text(row.get("status")),
        "error_kind": _nullable_text(row.get("error_kind")),
        "error_message": _nullable_text(row.get("error_message")),
    }


def _document_refs(
    documents: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "document_id": _text(document.get("document_id")),
            "file_name": _text(document.get("file_name")),
            "status": _text(document.get("status")),
            "processing_status": _nullable_text(document.get("processing_status")),
            "resume_policy": _nullable_text(document.get("resume_policy")),
        }
        for document in documents
    ]


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


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)

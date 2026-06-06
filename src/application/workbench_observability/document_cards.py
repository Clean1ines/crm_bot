from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.application.workbench.document_card_projection import (
    with_workbench_document_card_view,
)


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
            "project_id": project_id,
            "documents": documents,
            "items": documents,
            "total_count": len(documents),
            "limit": limit,
            "offset": offset,
        }


def _document_payload(row: Mapping[str, object]) -> dict[str, object]:
    """Build the document-list payload around the canonical Workbench card view.

    This module is intentionally only an HTTP/read-model adapter.
    It must not contain a second card lifecycle/timer/action builder.
    The only source of truth for card_view is:
    src.application.workbench.document_card_projection.with_workbench_document_card_view
    """

    canonical_document = with_workbench_document_card_view(dict(row))
    if not isinstance(canonical_document, Mapping):
        canonical_document = dict(row)

    card_view = _mapping(canonical_document.get("card_view"))
    sections = _mapping(card_view.get("sections"))
    registry = _mapping(card_view.get("registry"))
    runtime = _mapping(card_view.get("runtime"))
    usage = _mapping(card_view.get("usage"))
    timer = _mapping(card_view.get("timer"))

    document_id = _text(row.get("document_id"))
    file_size = _int(row.get("file_size_bytes"))
    status = _text(row.get("status")) or "uploaded"
    processing_status = _nullable_text(row.get("processing_status"))

    return {
        "id": document_id,
        "document_id": document_id,
        "project_id": _text(row.get("project_id")),
        "file_name": _text(row.get("file_name")) or "document",
        "source_type": _text(row.get("source_type")) or "markdown",
        "file_size": file_size,
        "file_size_bytes": file_size,
        "status": status,
        "preprocessing_mode": "faq",
        "preprocessing_status": processing_status or status,
        "structured_entries": _int(registry.get("entry_count")),
        "chunk_count": _int(sections.get("total")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "current_processing_run_id": _nullable_text(
            row.get("current_processing_run_id")
        )
        or _nullable_text(row.get("processing_run_id")),
        # Temporary top-level compatibility for legacy UI helpers.
        # Values are derived from canonical card_view, not rebuilt separately.
        "preprocessing_metrics": _compat_metrics(
            card_view=card_view,
            sections=sections,
            registry=registry,
            runtime=runtime,
            usage=usage,
            timer=timer,
        ),
        "card_view": card_view,
    }


def _compat_metrics(
    *,
    card_view: Mapping[str, object],
    sections: Mapping[str, object],
    registry: Mapping[str, object],
    runtime: Mapping[str, object],
    usage: Mapping[str, object],
    timer: Mapping[str, object],
) -> dict[str, object]:
    active_elapsed_seconds = _int(timer.get("active_elapsed_seconds"))

    return {
        "status_message": _text(card_view.get("default_status_description")),
        "raw_source_chunk_count": _int(sections.get("total")),
        "source_chunk_count": _int(sections.get("total")),
        "canonical_entry_count": _int(registry.get("entry_count")),
        "published_entry_count": _int(runtime.get("runtime_entry_count")),
        "llm_tokens_total": _int(usage.get("total_tokens")),
        # Compatibility only. Do not expose wall-time as processing timer.
        "elapsed_seconds": active_elapsed_seconds,
        "elapsed_before_resume_seconds": active_elapsed_seconds,
    }


def _mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return _nullable_text(value)

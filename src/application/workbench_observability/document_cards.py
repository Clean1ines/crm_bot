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

    document_id = _text(row.get("document_id"))
    file_size = _int(row.get("file_size_bytes"))
    status = _text(row.get("status")) or "uploaded"

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
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "current_processing_run_id": _nullable_text(
            row.get("current_processing_run_id")
        )
        or _nullable_text(row.get("processing_run_id")),
        "card_view": card_view,
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

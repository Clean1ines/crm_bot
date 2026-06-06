from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum

from src.application.workbench.document_card_builder import (
    WorkbenchDocumentCardSource,
    build_workbench_document_card_view,
)


def with_workbench_document_card_views(payload: object) -> object:
    """Attach card_view to Workbench document list payloads.

    The old API shape is preserved for temporary frontend compatibility.
    New Workbench UI must read item.card_view instead of inferring state from
    legacy counters.
    """

    if isinstance(payload, list):
        return [with_workbench_document_card_view(item) for item in payload]

    if not isinstance(payload, MutableMapping):
        return payload

    result: dict[str, object] = dict(payload)
    for key in ("documents", "items", "data"):
        value = result.get(key)
        if isinstance(value, list):
            result[key] = [with_workbench_document_card_view(item) for item in value]
            return result

    return result


def with_workbench_document_card_view(row: object) -> object:
    if not isinstance(row, Mapping):
        return row

    document: dict[str, object] = dict(row)
    card = build_workbench_document_card_view(card_source_from_document_row(row))
    document["card_view"] = to_jsonable(card)
    return document


def card_source_from_document_row(
    row: Mapping[str, object],
) -> WorkbenchDocumentCardSource:
    processing_status = _optional_str(row, "processing_status")
    current_started_at = (
        _datetime(row.get("started_at")) if _is_running(processing_status) else None
    )

    runtime_entry_count = _int(row, "runtime_entry_count")
    publication_id = _optional_str(row, "publication_id")
    if runtime_entry_count > 0 and publication_id is None:
        publication_id = f"publication-for-{_str(row, 'document_id')}"

    retention_state = _optional_str(row, "retention_state") or "active_processing"
    final_snapshot_id = _optional_str(row, "final_registry_snapshot_id")
    registry_retained = _bool(row, "registry_retained")
    if retention_state == "transient_purged" and final_snapshot_id is not None:
        registry_retained = True

    return WorkbenchDocumentCardSource(
        project_id=_str(row, "project_id"),
        document_id=_str(row, "document_id"),
        file_name=_str(row, "file_name"),
        source_type=_optional_str(row, "source_type") or "markdown",
        document_status=_optional_str(row, "status") or "uploaded",
        retention_state=retention_state,
        current_processing_run_id=_optional_str(row, "current_processing_run_id"),
        processing_status=processing_status,
        resume_policy=_optional_str(row, "resume_policy"),
        active_elapsed_seconds=_int(row, "active_elapsed_seconds"),
        wall_elapsed_seconds=_int(row, "wall_elapsed_seconds"),
        current_active_started_at=current_started_at,
        prompt_tokens=_int(row, "prompt_tokens"),
        completion_tokens=_int(row, "completion_tokens"),
        total_tokens=_int(row, "total_tokens"),
        llm_call_count=_int(row, "llm_call_count"),
        sections_total=_int(row, "section_count"),
        sections_processed=_int(row, "processed_section_count"),
        sections_failed=_int(row, "failed_section_count"),
        sections_pending=_int(row, "pending_section_count"),
        section_queue_ready_count=_int(row, "section_queue_ready_count"),
        section_queue_leased_count=_int(row, "section_queue_leased_count"),
        prompt_a_completed_sections=_int(row, "prompt_a_completed_sections"),
        section_queue_registry_application_queued_count=_int(
            row,
            "section_queue_registry_application_queued_count",
        ),
        section_queue_registry_application_applied_count=_int(
            row,
            "section_queue_registry_application_applied_count",
        ),
        section_queue_waiting_for_fresh_registry_count=_int(
            row,
            "section_queue_waiting_for_fresh_registry_count",
        ),
        section_queue_failed_count=_int(row, "section_queue_failed_count"),
        section_queue_total_attempt_count=_int(
            row,
            "section_queue_total_attempt_count",
        ),
        section_queue_max_attempt_count=_int(row, "section_queue_max_attempt_count"),
        registry_application_ready_count=_int(
            row,
            "registry_application_ready_count",
        ),
        registry_application_leased_count=_int(
            row,
            "registry_application_leased_count",
        ),
        registry_application_waiting_for_fresh_registry_count=_int(
            row,
            "registry_application_waiting_for_fresh_registry_count",
        ),
        registry_application_applied_count=_int(
            row,
            "registry_application_applied_count",
        ),
        registry_application_failed_count=_int(
            row,
            "registry_application_failed_count",
        ),
        embedding_indexed_claims=_int(row, "embedding_indexed_claims"),
        embedding_indexed_node_runs=_int(row, "embedding_indexed_node_runs"),
        canonical_fact_count=_int(row, "canonical_fact_count"),
        final_registry_snapshot_id=final_snapshot_id,
        registry_retained=registry_retained,
        surface_draft_count=_int(row, "surface_draft_count"),
        surface_ready_count=_int(row, "surface_ready_count"),
        surface_published_count=_int(row, "surface_published_count"),
        surface_rejected_count=_int(row, "surface_rejected_count"),
        curation_session_id=_optional_str(row, "curation_session_id"),
        curation_session_status=_optional_str(row, "curation_session_status"),
        publication_id=publication_id,
        runtime_entry_count=runtime_entry_count,
        auto_resume_scheduled_at=_datetime(row.get("auto_resume_scheduled_at")),
        last_error_kind=_optional_str(row, "processing_last_error_kind")
        or _optional_str(row, "last_error_kind"),
        last_user_message=_optional_str(row, "processing_last_user_message")
        or _optional_str(row, "last_error_message"),
        internal_error_ref=_optional_str(row, "last_error_report_id"),
    )


def to_jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    return value


def _is_running(value: str | None) -> bool:
    return (value or "").strip().lower() in {"pending", "running", "processing"}


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return str(value)


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


def _bool(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "published_retained"}
    return False


def _datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


__all__ = [
    "card_source_from_document_row",
    "to_jsonable",
    "with_workbench_document_card_view",
    "with_workbench_document_card_views",
]

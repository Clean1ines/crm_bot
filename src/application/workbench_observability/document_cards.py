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
            "project_id": project_id,
            "documents": documents,
            "items": documents,
            "total_count": len(documents),
            "limit": limit,
            "offset": offset,
        }


def _document_payload(row: Mapping[str, object]) -> dict[str, object]:
    document_id = _text(row.get("document_id"))
    file_size = _int(row.get("file_size_bytes"))
    status = _text(row.get("status")) or "uploaded"
    processing_status = _nullable_text(row.get("processing_status"))
    card_view = _card_view(row)
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
        "structured_entries": _int(row.get("canonical_fact_count")),
        "chunk_count": _int(row.get("section_count")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "current_processing_run_id": _nullable_text(row.get("current_processing_run_id"))
        or _nullable_text(row.get("processing_run_id")),
        "preprocessing_metrics": _legacy_metrics(row, card_view),
        "card_view": card_view,
    }


def _card_view(row: Mapping[str, object]) -> dict[str, object]:
    processing_status = _nullable_text(row.get("processing_status"))
    document_status = _text(row.get("status")) or "uploaded"
    lifecycle_state = processing_status or document_status
    runtime_entry_count = _int(row.get("runtime_entry_count"))
    is_published = runtime_entry_count > 0 or document_status == "published"
    is_running = lifecycle_state in {
        "pending",
        "queued",
        "running",
        "processing",
        "sectioned",
        "cancelling",
    }
    is_failed = lifecycle_state in {
        "failed",
        "error",
        "failed_validation",
        "cancelled_by_system",
    } or bool(_nullable_text(row.get("processing_last_error_kind")))
    is_completed = lifecycle_state == "completed" or document_status in {
        "processed",
        "completed",
    }
    return {
        "document_id": _text(row.get("document_id")),
        "project_id": _text(row.get("project_id")),
        "file_name": _text(row.get("file_name")) or "document",
        "source_type": _text(row.get("source_type")) or "markdown",
        "lifecycle_state": lifecycle_state,
        "retention_state": _text(row.get("retention_state")) or "active",
        "transient_purged": False,
        "resume_available": _resume_available(row, lifecycle_state),
        "status_i18n_key": f"knowledge.workbench.status.{_status_bucket(lifecycle_state)}",
        "default_status_label": _status_label(
            is_published=is_published,
            is_failed=is_failed,
            is_running=is_running,
            is_completed=is_completed,
        ),
        "status_description_i18n_key": (
            f"knowledge.workbench.statusDescription.{_status_bucket(lifecycle_state)}"
        ),
        "default_status_description": _status_description(
            is_published=is_published,
            is_failed=is_failed,
            is_running=is_running,
            is_completed=is_completed,
        ),
        "timer": _timer(row, lifecycle_state),
        "usage": {
            "prompt_tokens": _int(row.get("prompt_tokens")),
            "completion_tokens": _int(row.get("completion_tokens")),
            "total_tokens": _int(row.get("total_tokens")),
            "llm_call_count": _int(row.get("llm_call_count")),
            "i18n_key": "knowledge.workbench.usage.llm",
        },
        "sections": {
            "total": _int(row.get("section_count")),
            "processed": _int(row.get("processed_section_count")),
            "failed": _int(row.get("failed_section_count")),
            "pending": _int(row.get("pending_section_count")),
        },
        "registry": {
            "entry_count": _int(row.get("canonical_fact_count")),
            "final_snapshot_id": _nullable_text(row.get("final_registry_snapshot_id")),
            "retained": _bool(row.get("registry_retained")),
        },
        "runtime": {
            "publication_id": _nullable_text(row.get("publication_id")),
            "runtime_entry_count": runtime_entry_count,
        },
        "recovery": _recovery(row),
        "actions": _actions(row, lifecycle_state),
        "messages": _messages(row, lifecycle_state),
        "error": _error(row),
        "metadata": {
            "processing_run_id": _nullable_text(row.get("processing_run_id")),
            "processing_status": processing_status,
            "processing_trigger": _nullable_text(row.get("processing_trigger")),
        },
    }


def _legacy_metrics(row: Mapping[str, object], card_view: Mapping[str, object]) -> dict[str, object]:
    return {
        "status_message": card_view["default_status_description"],
        "raw_source_chunk_count": _int(row.get("section_count")),
        "source_chunk_count": _int(row.get("section_count")),
        "canonical_entry_count": _int(row.get("canonical_fact_count")),
        "published_entry_count": _int(row.get("runtime_entry_count")),
        "llm_tokens_total": _int(row.get("total_tokens")),
        "elapsed_seconds": _int(row.get("wall_elapsed_seconds")),
        "elapsed_before_resume_seconds": _int(row.get("active_elapsed_seconds")),
    }


def _timer(row: Mapping[str, object], lifecycle_state: str) -> dict[str, object]:
    mode = (
        "running"
        if lifecycle_state in {"pending", "queued", "running", "processing", "sectioned"}
        else "stopped"
    )
    if lifecycle_state in {"completed", "processed"}:
        mode = "completed"
    if lifecycle_state == "published":
        mode = "published"
    if lifecycle_state in {"paused_quota", "paused_provider", "paused_server_interrupted"}:
        mode = "paused"
    return {
        "mode": mode,
        "active_elapsed_seconds": _int(row.get("active_elapsed_seconds")),
        "wall_elapsed_seconds": _int(row.get("wall_elapsed_seconds")),
        "current_active_started_at": _iso(row.get("started_at")) if mode == "running" else None,
        "i18n_key": f"knowledge.workbench.timer.{mode}",
        "default_label": {
            "running": "Обработка идёт",
            "paused": "Обработка на паузе",
            "completed": "Обработка завершена",
            "published": "Опубликовано",
        }.get(mode, "Обработка остановлена"),
    }


def _recovery(row: Mapping[str, object]) -> dict[str, object]:
    resume_policy = _nullable_text(row.get("resume_policy")) or "none"
    scheduled_at = _iso(row.get("auto_resume_scheduled_at"))
    if scheduled_at:
        mode = "scheduled_auto_resume"
    elif resume_policy in {"explicit_user_action", "manual_only"}:
        mode = "manual_only"
    elif resume_policy == "forbidden":
        mode = "forbidden"
    else:
        mode = "none"
    return {
        "mode": mode,
        "scheduled_at": scheduled_at,
        "can_cancel_scheduled_resume": bool(scheduled_at),
        "reason_code": resume_policy,
        "i18n_key": f"knowledge.workbench.recovery.{mode}",
        "default_message": {
            "scheduled_auto_resume": "Автовосстановление запланировано",
            "manual_only": "Продолжение доступно вручную",
            "forbidden": "Продолжение запрещено после ошибки",
        }.get(mode, "Восстановление не требуется"),
    }


def _actions(row: Mapping[str, object], lifecycle_state: str) -> list[dict[str, object]]:
    running = lifecycle_state in {"pending", "queued", "running", "processing", "sectioned"}
    resume = _resume_available(row, lifecycle_state)
    publish_ready = _int(row.get("canonical_fact_count")) > 0
    return [
        _action("cancel_processing", visible=running, enabled=running, tone="warning", label="Остановить"),
        _action("resume_processing", visible=resume, enabled=resume, tone="primary", label="Продолжить обработку"),
        _action("open_curation", visible=True, enabled=True, tone="secondary", label="Trace"),
        _action("publish_ready", visible=publish_ready, enabled=publish_ready and not running, tone="primary", label="Опубликовать"),
        _action("delete_document", visible=True, enabled=True, tone="danger", label="Удалить", confirmation="Удалить документ?"),
    ]


def _action(
    action_id: str,
    *,
    visible: bool,
    enabled: bool,
    tone: str,
    label: str,
    confirmation: str | None = None,
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "visible": visible,
        "enabled": enabled,
        "tone": tone,
        "i18n_key": f"knowledge.workbench.actions.{action_id}",
        "default_label": label,
        "reason_code": None,
        "confirmation_i18n_key": None,
        "default_confirmation": confirmation,
    }


def _messages(row: Mapping[str, object], lifecycle_state: str) -> list[dict[str, object]]:
    error_message = _nullable_text(row.get("processing_last_user_message")) or _nullable_text(row.get("last_error_message"))
    if error_message:
        return [{"code": _nullable_text(row.get("processing_last_error_kind")) or "processing_error", "severity": "error", "i18n_key": "knowledge.workbench.messages.processingError", "default_message": error_message, "debug_ref": _nullable_text(row.get("last_error_report_id"))}]
    if lifecycle_state in {"pending", "queued", "running", "processing", "sectioned"}:
        return [{"code": "processing", "severity": "info", "i18n_key": "knowledge.workbench.messages.processing", "default_message": "Документ принят и обрабатывается Workbench-пайплайном.", "debug_ref": None}]
    return []


def _error(row: Mapping[str, object]) -> dict[str, object] | None:
    message = _nullable_text(row.get("processing_last_user_message")) or _nullable_text(row.get("last_error_message"))
    if not message:
        return None
    reason = _nullable_text(row.get("processing_last_error_kind")) or "processing_error"
    return {"reason_code": reason, "user_message": {"code": reason, "severity": "error", "i18n_key": "knowledge.workbench.error.processing", "default_message": message, "debug_ref": _nullable_text(row.get("last_error_report_id"))}, "recoverable": _resume_available(row, _nullable_text(row.get("processing_status")) or ""), "retry_available": _resume_available(row, _nullable_text(row.get("processing_status")) or ""), "internal_error_ref": _nullable_text(row.get("last_error_report_id"))}


def _resume_available(row: Mapping[str, object], lifecycle_state: str) -> bool:
    return _nullable_text(row.get("resume_policy")) in {"explicit_user_action", "manual_only"} or lifecycle_state == "cancelled_by_user"


def _status_bucket(lifecycle_state: str) -> str:
    if lifecycle_state in {"pending", "queued", "running", "processing", "sectioned"}:
        return "processing"
    if lifecycle_state in {"completed", "processed"}:
        return "completed"
    if lifecycle_state in {"failed", "error", "failed_validation"}:
        return "failed"
    if lifecycle_state.startswith("paused"):
        return "paused"
    return lifecycle_state or "unknown"


def _status_label(*, is_published: bool, is_failed: bool, is_running: bool, is_completed: bool) -> str:
    if is_published:
        return "Опубликовано"
    if is_failed:
        return "Ошибка обработки"
    if is_running:
        return "Обрабатывается"
    if is_completed:
        return "Обработано"
    return "Загружено"


def _status_description(*, is_published: bool, is_failed: bool, is_running: bool, is_completed: bool) -> str:
    if is_published:
        return "Факты опубликованы в runtime retrieval."
    if is_failed:
        return "Обработка остановлена ошибкой."
    if is_running:
        return "Документ обрабатывается Workbench-пайплайном."
    if is_completed:
        return "Документ обработан."
    return "Документ загружен и ожидает обработки."


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
    try:
        return int(str(value))
    except ValueError:
        return 0


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return _nullable_text(value)

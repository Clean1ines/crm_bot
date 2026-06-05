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

        total_sections = sum(_int(document["section_count"]) for document in documents)
        processed_sections = sum(
            _int(document["processed_section_count"]) for document in documents
        )
        failed_sections = sum(
            _int(document["failed_section_count"]) for document in documents
        )
        pending_sections = sum(
            _int(document["pending_section_count"]) for document in documents
        )

        return {
            "project_id": project_id,
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
            "active_document_ids": [
                _text(document.get("document_id")) for document in active_documents
            ],
            "failed_document_ids": [
                _text(document.get("document_id")) for document in failed_documents
            ],
            "resumable_document_ids": [
                _text(document.get("document_id")) for document in resumable_documents
            ],
        }


def _document_payload(row: Mapping[str, object]) -> dict[str, object]:
    document_id = _text(row.get("document_id"))
    section_count = _int(row.get("section_count"))
    processed_count = _int(row.get("processed_section_count"))
    failed_count = _int(row.get("failed_section_count"))
    pending_count = _int(row.get("pending_section_count"))
    processing_status = _nullable_text(row.get("processing_status"))
    status = processing_status or _text(row.get("status"))
    card_view = _card_view(
        row,
        document_id=document_id,
        status=status,
        section_count=section_count,
        processed_count=processed_count,
        failed_count=failed_count,
        pending_count=pending_count,
    )

    return {
        "id": document_id,
        "document_id": document_id,
        "project_id": _text(row.get("project_id")),
        "file_name": _text(row.get("file_name")),
        "source_type": _text(row.get("source_type")),
        "file_size": _int(row.get("file_size_bytes")),
        "file_size_bytes": _int(row.get("file_size_bytes")),
        "status": _text(row.get("status")),
        "preprocessing_mode": "faq",
        "preprocessing_status": status,
        "processing_run_id": _nullable_text(row.get("processing_run_id")),
        "processing_status": processing_status,
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
        "chunk_count": section_count,
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "started_at": _iso(row.get("started_at")),
        "completed_at": _iso(row.get("completed_at")),
        "last_error_kind": _nullable_text(row.get("last_error_kind")),
        "last_error_message": _nullable_text(row.get("last_error_message")),
        "last_error_at": _iso(row.get("last_error_at")),
        "card_view": card_view,
    }


def _card_view(
    row: Mapping[str, object],
    *,
    document_id: str,
    status: str,
    section_count: int,
    processed_count: int,
    failed_count: int,
    pending_count: int,
) -> dict[str, object]:
    running = status in {"pending", "queued", "running", "processing", "sectioned"}
    failed = status in {"failed", "failed_validation", "error"} or bool(
        _nullable_text(row.get("last_error_kind"))
    )
    completed = status in {"completed", "processed"}
    return {
        "document_id": document_id,
        "project_id": _text(row.get("project_id")),
        "file_name": _text(row.get("file_name")),
        "source_type": _text(row.get("source_type")),
        "lifecycle_state": status,
        "retention_state": "active",
        "transient_purged": False,
        "resume_available": _nullable_text(row.get("resume_policy"))
        == "explicit_user_action",
        "status_i18n_key": f"knowledge.workbench.status.{_status_bucket(status)}",
        "default_status_label": _status_label(
            failed=failed, running=running, completed=completed
        ),
        "status_description_i18n_key": "knowledge.workbench.statusDescription.processing",
        "default_status_description": _status_description(
            failed=failed, running=running, completed=completed
        ),
        "timer": {
            "mode": "running" if running else "stopped",
            "active_elapsed_seconds": 0,
            "wall_elapsed_seconds": 0,
            "current_active_started_at": _iso(row.get("started_at"))
            if running
            else None,
            "i18n_key": "knowledge.workbench.timer.running"
            if running
            else "knowledge.workbench.timer.stopped",
            "default_label": "Обработка идёт" if running else "Обработка остановлена",
        },
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_call_count": 0,
            "i18n_key": "knowledge.workbench.usage.llm",
        },
        "sections": {
            "total": section_count,
            "processed": processed_count,
            "failed": failed_count,
            "pending": pending_count,
        },
        "registry": {
            "entry_count": 0,
            "final_snapshot_id": None,
            "retained": False,
        },
        "runtime": {
            "publication_id": None,
            "runtime_entry_count": 0,
        },
        "recovery": {
            "mode": "manual_only"
            if _nullable_text(row.get("resume_policy")) == "explicit_user_action"
            else "none",
            "scheduled_at": None,
            "can_cancel_scheduled_resume": False,
            "reason_code": _nullable_text(row.get("resume_policy")) or "none",
            "i18n_key": "knowledge.workbench.recovery.none",
            "default_message": "Восстановление не требуется",
        },
        "actions": _actions(
            running=running,
            resumable=_nullable_text(row.get("resume_policy"))
            == "explicit_user_action",
        ),
        "messages": _messages(row, running=running),
        "error": _error(row) if failed else None,
        "metadata": {
            "processing_run_id": _nullable_text(row.get("processing_run_id")),
            "processing_status": _nullable_text(row.get("processing_status")),
            "processing_trigger": _nullable_text(row.get("processing_trigger")),
        },
    }


def _actions(*, running: bool, resumable: bool) -> list[dict[str, object]]:
    return [
        _action(
            "cancel_processing",
            visible=running,
            enabled=running,
            tone="warning",
            label="Остановить",
        ),
        _action(
            "resume_processing",
            visible=resumable,
            enabled=resumable,
            tone="primary",
            label="Продолжить обработку",
        ),
        _action(
            "open_curation", visible=True, enabled=True, tone="secondary", label="Trace"
        ),
        _action(
            "delete_document",
            visible=True,
            enabled=True,
            tone="danger",
            label="Удалить",
        ),
    ]


def _action(
    action_id: str, *, visible: bool, enabled: bool, tone: str, label: str
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
        "default_confirmation": None,
    }


def _messages(row: Mapping[str, object], *, running: bool) -> list[dict[str, object]]:
    error_message = _nullable_text(row.get("last_error_message"))
    if error_message:
        return [
            {
                "code": _nullable_text(row.get("last_error_kind"))
                or "processing_error",
                "severity": "error",
                "i18n_key": "knowledge.workbench.messages.processingError",
                "default_message": error_message,
                "debug_ref": None,
            }
        ]
    if running:
        return [
            {
                "code": "processing",
                "severity": "info",
                "i18n_key": "knowledge.workbench.messages.processing",
                "default_message": "Документ обрабатывается Workbench-пайплайном.",
                "debug_ref": None,
            }
        ]
    return []


def _error(row: Mapping[str, object]) -> dict[str, object] | None:
    message = _nullable_text(row.get("last_error_message"))
    if not message:
        return None
    reason = _nullable_text(row.get("last_error_kind")) or "processing_error"
    return {
        "reason_code": reason,
        "user_message": {
            "code": reason,
            "severity": "error",
            "i18n_key": "knowledge.workbench.error.processing",
            "default_message": message,
            "debug_ref": None,
        },
        "recoverable": False,
        "retry_available": False,
        "internal_error_ref": None,
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


def _status_bucket(status: str) -> str:
    if status in {"pending", "queued", "running", "processing", "sectioned"}:
        return "processing"
    if status in {"completed", "processed"}:
        return "completed"
    if status in {"failed", "failed_validation", "error"}:
        return "failed"
    return status or "unknown"


def _status_label(*, failed: bool, running: bool, completed: bool) -> str:
    if failed:
        return "Ошибка обработки"
    if running:
        return "Обрабатывается"
    if completed:
        return "Обработано"
    return "Загружено"


def _status_description(*, failed: bool, running: bool, completed: bool) -> str:
    if failed:
        return "Обработка остановлена ошибкой."
    if running:
        return "Документ обрабатывается Workbench-пайплайном."
    if completed:
        return "Документ обработан."
    return "Документ загружен."


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
    return int(str(value))


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)

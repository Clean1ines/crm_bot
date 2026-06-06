from __future__ import annotations

from datetime import datetime, timezone

from src.application.workbench.document_card_projection import (
    card_source_from_document_row,
    with_workbench_document_card_view,
    with_workbench_document_card_views,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_projection_builds_running_card_view_from_document_row() -> None:
    row = {
        "project_id": "project-1",
        "document_id": "document-1",
        "file_name": "faq.md",
        "source_type": "markdown",
        "status": "processing",
        "retention_state": "active_processing",
        "current_processing_run_id": "run-1",
        "processing_status": "running",
        "resume_policy": "manual_only",
        "started_at": _NOW,
        "current_active_started_at": _NOW,
        "active_elapsed_seconds": 90,
        "wall_elapsed_seconds": 120,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "llm_call_count": 3,
        "section_count": 10,
        "processed_section_count": 2,
        "failed_section_count": 0,
        "pending_section_count": 8,
    }

    projected = with_workbench_document_card_view(row)

    assert projected["card_view"]["lifecycle_state"] == "processing"
    assert projected["card_view"]["timer"]["mode"] == "running"
    assert (
        projected["card_view"]["timer"]["current_active_started_at"] == _NOW.isoformat()
    )
    assert projected["card_view"]["usage"]["total_tokens"] == 150
    assert projected["card_view"]["actions"][0]["action_id"] == "cancel_processing"


def test_projection_builds_transient_purged_published_card_without_resume() -> None:
    row = {
        "project_id": "project-1",
        "document_id": "document-1",
        "file_name": "faq.md",
        "source_type": "markdown",
        "status": "published",
        "retention_state": "transient_purged",
        "current_processing_run_id": None,
        "active_elapsed_seconds": 600,
        "wall_elapsed_seconds": 900,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
        "llm_call_count": 12,
        "canonical_fact_count": 8,
        "final_registry_snapshot_id": "snapshot-final",
        "registry_retained": True,
        "surface_published_count": 8,
        "publication_id": "publication-1",
        "runtime_entry_count": 8,
    }

    projected = with_workbench_document_card_view(row)
    card = projected["card_view"]

    assert card["lifecycle_state"] == "transient_purged"
    assert card["retention_state"] == "transient_purged"
    assert card["transient_purged"] is True
    assert card["resume_available"] is False
    assert card["registry"]["retained"] is True
    assert card["runtime"]["runtime_entry_count"] == 8
    assert any(
        action["action_id"] == "resume_processing" and not action["enabled"]
        for action in card["actions"]
    )
    assert card["messages"][0]["default_message"] == (
        "Документ опубликован. Промежуточные данные очищены."
    )


def test_projection_enriches_documents_payload_without_removing_legacy_fields() -> None:
    payload = {
        "documents": [
            {
                "project_id": "project-1",
                "document_id": "document-1",
                "file_name": "faq.md",
                "status": "processed",
                "processing_status": "completed",
                "section_count": 1,
                "processed_section_count": 1,
                "surface_ready_count": 1,
                "curation_session_id": "curation-1",
                "curation_session_status": "open",
            }
        ],
        "limit": 50,
        "offset": 0,
    }

    projected = with_workbench_document_card_views(payload)

    assert projected["documents"][0]["document_id"] == "document-1"
    assert (
        projected["documents"][0]["card_view"]["lifecycle_state"]
        == "ready_for_curation"
    )
    assert (
        projected["documents"][0]["card_view"]["actions"][0]["action_id"]
        == "open_curation"
    )


def test_card_source_from_document_row_prefers_processing_error_message() -> None:
    source = card_source_from_document_row(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "status": "processing",
            "current_processing_run_id": "run-1",
            "processing_status": "failed",
            "resume_policy": "manual_only",
            "processing_last_error_kind": "provider_error",
            "last_error_kind": "old_document_error",
            "processing_last_user_message": "Провайдер ИИ временно недоступен.",
            "last_error_message": "Old error",
        }
    )

    assert source.last_error_kind == "provider_error"
    assert source.last_user_message == "Провайдер ИИ временно недоступен."

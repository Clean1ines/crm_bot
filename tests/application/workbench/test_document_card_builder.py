from __future__ import annotations

from datetime import datetime, timezone

from src.application.workbench.document_card_builder import (
    WorkbenchDocumentCardSource,
    build_workbench_document_card_view,
)
from src.application.workbench.document_card_contract import (
    WorkbenchCardActionId,
    WorkbenchCardMessageSeverity,
    WorkbenchDocumentLifecycleState,
    WorkbenchTimerMode,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_builder_maps_running_document_to_timer_tokens_and_stop_action() -> None:
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="processing",
            current_processing_run_id="run-1",
            processing_status="running",
            active_elapsed_seconds=90,
            wall_elapsed_seconds=120,
            current_active_started_at=_NOW,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            llm_call_count=3,
            sections_total=10,
            sections_processed=2,
            sections_pending=8,
        )
    )

    assert card.lifecycle_state is WorkbenchDocumentLifecycleState.PROCESSING
    assert card.timer.mode is WorkbenchTimerMode.RUNNING
    assert card.timer.current_active_started_at is _NOW
    assert card.usage.total_tokens == 150
    assert card.action(WorkbenchCardActionId.CANCEL_PROCESSING).enabled is True
    assert card.action(WorkbenchCardActionId.DELETE_DOCUMENT).enabled is True
    assert card.messages[0].default_message.startswith("Документ обрабатывается")


def test_builder_maps_auto_recovery_to_cancel_scheduled_recovery_action() -> None:
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="processing",
            current_processing_run_id="run-1",
            processing_status="paused_provider",
            resume_policy="auto_allowed",
            auto_resume_scheduled_at=_NOW,
            active_elapsed_seconds=120,
            wall_elapsed_seconds=360,
            last_error_kind="provider_error",
            last_user_message="Провайдер ИИ временно недоступен.",
        )
    )

    assert (
        card.lifecycle_state is WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED
    )
    assert card.recovery.can_cancel_scheduled_resume is True
    assert card.action(WorkbenchCardActionId.CANCEL_SCHEDULED_RECOVERY).enabled is True
    assert card.action(WorkbenchCardActionId.RESUME_PROCESSING).enabled is True
    assert card.messages[0].default_message == (
        "Обработка приостановлена. Автопродолжение уже запланировано."
    )


def test_builder_maps_manual_pause_to_resume_action_and_user_error_message() -> None:
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="processing",
            current_processing_run_id="run-1",
            processing_status="failed",
            resume_policy="manual_only",
            active_elapsed_seconds=120,
            wall_elapsed_seconds=360,
            last_error_kind="provider_error",
            last_user_message="Провайдер ИИ временно недоступен. Можно попробовать позже.",
            internal_error_ref="node-run-1",
        )
    )

    assert card.lifecycle_state is WorkbenchDocumentLifecycleState.PAUSED_PROVIDER
    assert card.resume_available is True
    assert card.action(WorkbenchCardActionId.RESUME_PROCESSING).enabled is True
    assert card.error is not None
    assert card.error.user_message.default_message == (
        "Провайдер ИИ временно недоступен. Можно попробовать позже."
    )
    assert any(
        message.severity is WorkbenchCardMessageSeverity.ERROR
        for message in card.messages
    )


def test_builder_maps_ready_for_curation_to_curation_modal_action() -> None:
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="processed",
            processing_status="completed",
            active_elapsed_seconds=600,
            wall_elapsed_seconds=800,
            sections_total=10,
            sections_processed=10,
            canonical_fact_count=8,
            surface_ready_count=8,
            curation_session_id="curation-1",
            curation_session_status="open",
        )
    )

    assert card.lifecycle_state is WorkbenchDocumentLifecycleState.READY_FOR_CURATION
    assert card.action(WorkbenchCardActionId.OPEN_CURATION).enabled is True
    assert card.surfaces.ready_count == 8
    assert card.messages[0].default_message == (
        "Черновики карточек готовы. Проверьте их в курации."
    )


def test_builder_maps_publish_pending_to_publish_ready_action() -> None:
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="processed",
            processing_status="completed",
            active_elapsed_seconds=600,
            wall_elapsed_seconds=800,
            sections_total=10,
            sections_processed=10,
            canonical_fact_count=8,
            surface_ready_count=8,
            curation_session_id="curation-1",
            curation_session_status="publish_pending",
        )
    )

    assert card.lifecycle_state is WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION
    assert card.action(WorkbenchCardActionId.OPEN_CURATION).enabled is True
    assert card.action(WorkbenchCardActionId.PUBLISH_READY).enabled is True


def test_builder_maps_transient_purged_to_published_cleaned_card_without_resume() -> (
    None
):
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="published",
            retention_state="transient_purged",
            current_processing_run_id=None,
            active_elapsed_seconds=600,
            wall_elapsed_seconds=900,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            llm_call_count=12,
            canonical_fact_count=8,
            final_registry_snapshot_id="snapshot-final",
            registry_retained=True,
            surface_published_count=8,
            publication_id="publication-1",
            runtime_entry_count=8,
        )
    )

    assert card.lifecycle_state is WorkbenchDocumentLifecycleState.TRANSIENT_PURGED
    assert card.transient_purged is True
    assert card.resume_available is False
    assert card.action(WorkbenchCardActionId.RESUME_PROCESSING).enabled is False
    assert card.action(WorkbenchCardActionId.OPEN_PUBLISHED_SURFACES).enabled is True
    assert card.registry.retained is True
    assert card.runtime.runtime_entry_count == 8
    assert card.messages[0].default_message == (
        "Документ опубликован. Промежуточные данные очищены."
    )


def test_builder_delete_confirmation_distinguishes_published_knowledge() -> None:
    card = build_workbench_document_card_view(
        WorkbenchDocumentCardSource(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            document_status="published",
            retention_state="transient_purged",
            canonical_fact_count=1,
            final_registry_snapshot_id="snapshot-final",
            registry_retained=True,
            publication_id="publication-1",
            runtime_entry_count=1,
        )
    )

    delete_action = card.action(WorkbenchCardActionId.DELETE_DOCUMENT)

    assert delete_action is not None
    assert delete_action.default_confirmation == (
        "Удалить опубликованные знания этого документа из проекта?"
    )

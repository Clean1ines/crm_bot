from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.workbench.document_card_contract import (
    WorkbenchCardActionId,
    WorkbenchCardActionTone,
    WorkbenchCardActionView,
    WorkbenchCardErrorView,
    WorkbenchCardMessageSeverity,
    WorkbenchCardReasonCode,
    WorkbenchCardTimerView,
    WorkbenchCardUsageView,
    WorkbenchCardUserMessage,
    WorkbenchDocumentCardView,
    WorkbenchDocumentLifecycleState,
    WorkbenchDocumentRetentionState,
    WorkbenchRecoveryMode,
    WorkbenchRecoveryView,
    WorkbenchRegistrySummaryView,
    WorkbenchRuntimeSummaryView,
    WorkbenchSectionSummaryView,
    WorkbenchSurfaceSummaryView,
    WorkbenchTimerMode,
)


_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _timer(
    mode: WorkbenchTimerMode = WorkbenchTimerMode.PAUSED,
) -> WorkbenchCardTimerView:
    return WorkbenchCardTimerView(
        mode=mode,
        active_elapsed_seconds=120,
        wall_elapsed_seconds=300,
        current_active_started_at=_NOW if mode is WorkbenchTimerMode.RUNNING else None,
        i18n_key="knowledge.workbench.card.timer.running"
        if mode is WorkbenchTimerMode.RUNNING
        else "knowledge.workbench.card.timer.paused",
        default_label="Идёт обработка"
        if mode is WorkbenchTimerMode.RUNNING
        else "На паузе",
    )


def _usage() -> WorkbenchCardUsageView:
    return WorkbenchCardUsageView(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        llm_call_count=3,
    )


def _sections() -> WorkbenchSectionSummaryView:
    return WorkbenchSectionSummaryView(total=10, processed=8, failed=0, pending=2)


def _registry(retained: bool = False) -> WorkbenchRegistrySummaryView:
    return WorkbenchRegistrySummaryView(
        entry_count=7,
        final_snapshot_id="snapshot-final" if retained else None,
        retained=retained,
    )


def _surfaces(
    *,
    ready: int = 0,
    published: int = 0,
) -> WorkbenchSurfaceSummaryView:
    return WorkbenchSurfaceSummaryView(
        draft_count=0,
        ready_count=ready,
        published_count=published,
        rejected_count=0,
    )


def _runtime(published: bool = False) -> WorkbenchRuntimeSummaryView:
    return WorkbenchRuntimeSummaryView(
        publication_id="publication-1" if published else None,
        runtime_entry_count=published and 7 or 0,
    )


def _recovery(
    mode: WorkbenchRecoveryMode = WorkbenchRecoveryMode.NONE,
) -> WorkbenchRecoveryView:
    return WorkbenchRecoveryView(
        mode=mode,
        scheduled_at=_NOW
        if mode is WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME
        else None,
        can_cancel_scheduled_resume=mode is WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME,
        reason_code=WorkbenchCardReasonCode.AUTO_RESUME_SCHEDULED
        if mode is WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME
        else WorkbenchCardReasonCode.RUNNING,
        i18n_key="knowledge.workbench.card.recovery.autoScheduled"
        if mode is WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME
        else "knowledge.workbench.card.recovery.none",
        default_message="Автопродолжение запланировано"
        if mode is WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME
        else "Автопродолжение не запланировано",
    )


def _action(
    action_id: WorkbenchCardActionId,
    *,
    visible: bool = True,
    enabled: bool = True,
    tone: WorkbenchCardActionTone = WorkbenchCardActionTone.SECONDARY,
    label: str | None = None,
    reason_code: WorkbenchCardReasonCode | None = None,
) -> WorkbenchCardActionView:
    return WorkbenchCardActionView(
        action_id=action_id,
        visible=visible,
        enabled=enabled,
        tone=tone,
        i18n_key=f"knowledge.workbench.card.actions.{action_id.value}",
        default_label=label or action_id.value,
        reason_code=reason_code,
    )


def _message(
    code: WorkbenchCardReasonCode,
    *,
    severity: WorkbenchCardMessageSeverity = WorkbenchCardMessageSeverity.INFO,
    text: str = "Понятное сообщение для пользователя",
) -> WorkbenchCardUserMessage:
    return WorkbenchCardUserMessage(
        code=code,
        severity=severity,
        i18n_key=f"knowledge.workbench.card.messages.{code.value}",
        default_message=text,
    )


def test_running_card_has_ticking_timer_tokens_and_cancel_action() -> None:
    card = WorkbenchDocumentCardView(
        document_id="document-1",
        project_id="project-1",
        file_name="faq.md",
        source_type="markdown",
        lifecycle_state=WorkbenchDocumentLifecycleState.PROCESSING,
        retention_state=WorkbenchDocumentRetentionState.ACTIVE_PROCESSING,
        transient_purged=False,
        resume_available=False,
        status_i18n_key="knowledge.workbench.card.status.processing",
        default_status_label="Обрабатывается",
        status_description_i18n_key="knowledge.workbench.card.status.processingDescription",
        default_status_description="Документ разбирается на знания.",
        timer=_timer(WorkbenchTimerMode.RUNNING),
        usage=_usage(),
        sections=_sections(),
        registry=_registry(),
        surfaces=_surfaces(),
        runtime=_runtime(),
        recovery=_recovery(),
        actions=(
            _action(
                WorkbenchCardActionId.CANCEL_PROCESSING,
                tone=WorkbenchCardActionTone.WARNING,
                label="Остановить обработку",
            ),
            _action(
                WorkbenchCardActionId.DELETE_DOCUMENT,
                tone=WorkbenchCardActionTone.DANGER,
                label="Удалить документ",
            ),
        ),
        messages=(_message(WorkbenchCardReasonCode.RUNNING),),
    )

    assert card.timer.mode is WorkbenchTimerMode.RUNNING
    assert card.timer.current_active_started_at is _NOW
    assert card.usage.total_tokens == 150
    assert card.action(WorkbenchCardActionId.CANCEL_PROCESSING).enabled is True


def test_auto_recovery_card_requires_cancel_scheduled_recovery_action() -> None:
    card = WorkbenchDocumentCardView(
        document_id="document-1",
        project_id="project-1",
        file_name="faq.md",
        source_type="markdown",
        lifecycle_state=WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED,
        retention_state=WorkbenchDocumentRetentionState.ACTIVE_PROCESSING,
        transient_purged=False,
        resume_available=True,
        status_i18n_key="knowledge.workbench.card.status.autoRecoveryScheduled",
        default_status_label="Обработка приостановлена",
        status_description_i18n_key=(
            "knowledge.workbench.card.status.autoRecoveryScheduledDescription"
        ),
        default_status_description="Автопродолжение запланировано.",
        timer=_timer(),
        usage=_usage(),
        sections=_sections(),
        registry=_registry(),
        surfaces=_surfaces(),
        runtime=_runtime(),
        recovery=_recovery(WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME),
        actions=(
            _action(
                WorkbenchCardActionId.RESUME_PROCESSING,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Продолжить сейчас",
            ),
            _action(
                WorkbenchCardActionId.CANCEL_SCHEDULED_RECOVERY,
                label="Отменить автопродолжение",
            ),
        ),
        messages=(
            _message(
                WorkbenchCardReasonCode.AUTO_RESUME_SCHEDULED,
                severity=WorkbenchCardMessageSeverity.WARNING,
                text="Мы попробуем продолжить автоматически.",
            ),
        ),
    )

    assert card.recovery.can_cancel_scheduled_resume is True
    assert card.action(WorkbenchCardActionId.CANCEL_SCHEDULED_RECOVERY).enabled is True


def test_auto_recovery_card_rejects_missing_cancel_scheduled_recovery_action() -> None:
    with pytest.raises(ValueError, match="cancel scheduled recovery"):
        WorkbenchDocumentCardView(
            document_id="document-1",
            project_id="project-1",
            file_name="faq.md",
            source_type="markdown",
            lifecycle_state=WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED,
            retention_state=WorkbenchDocumentRetentionState.ACTIVE_PROCESSING,
            transient_purged=False,
            resume_available=True,
            status_i18n_key="knowledge.workbench.card.status.autoRecoveryScheduled",
            default_status_label="Обработка приостановлена",
            status_description_i18n_key=(
                "knowledge.workbench.card.status.autoRecoveryScheduledDescription"
            ),
            default_status_description="Автопродолжение запланировано.",
            timer=_timer(),
            usage=_usage(),
            sections=_sections(),
            registry=_registry(),
            surfaces=_surfaces(),
            runtime=_runtime(),
            recovery=_recovery(WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME),
            actions=(),
            messages=(_message(WorkbenchCardReasonCode.AUTO_RESUME_SCHEDULED),),
        )


def test_curatable_card_requires_open_curation_action() -> None:
    card = WorkbenchDocumentCardView(
        document_id="document-1",
        project_id="project-1",
        file_name="faq.md",
        source_type="markdown",
        lifecycle_state=WorkbenchDocumentLifecycleState.READY_FOR_CURATION,
        retention_state=WorkbenchDocumentRetentionState.ACTIVE_PROCESSING,
        transient_purged=False,
        resume_available=False,
        status_i18n_key="knowledge.workbench.card.status.readyForCuration",
        default_status_label="Готово к курации",
        status_description_i18n_key="knowledge.workbench.card.status.readyForCurationDescription",
        default_status_description="Проверьте карточки знаний перед публикацией.",
        timer=_timer(WorkbenchTimerMode.COMPLETED),
        usage=_usage(),
        sections=WorkbenchSectionSummaryView(
            total=10, processed=10, failed=0, pending=0
        ),
        registry=_registry(),
        surfaces=_surfaces(ready=7),
        runtime=_runtime(),
        recovery=_recovery(),
        actions=(
            _action(
                WorkbenchCardActionId.OPEN_CURATION,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Открыть курацию",
            ),
            _action(
                WorkbenchCardActionId.DELETE_DOCUMENT,
                tone=WorkbenchCardActionTone.DANGER,
                label="Удалить документ",
            ),
        ),
        messages=(_message(WorkbenchCardReasonCode.READY_FOR_CURATION),),
    )

    assert card.action(WorkbenchCardActionId.OPEN_CURATION).enabled is True


def test_transient_purged_card_forbids_resume_and_shows_cleaned_workspace_message() -> (
    None
):
    card = WorkbenchDocumentCardView(
        document_id="document-1",
        project_id="project-1",
        file_name="faq.md",
        source_type="markdown",
        lifecycle_state=WorkbenchDocumentLifecycleState.TRANSIENT_PURGED,
        retention_state=WorkbenchDocumentRetentionState.TRANSIENT_PURGED,
        transient_purged=True,
        resume_available=False,
        status_i18n_key="knowledge.workbench.card.status.published",
        default_status_label="Опубликовано",
        status_description_i18n_key="knowledge.workbench.card.status.transientPurgedDescription",
        default_status_description="Промежуточные данные очищены.",
        timer=_timer(WorkbenchTimerMode.PUBLISHED),
        usage=_usage(),
        sections=WorkbenchSectionSummaryView(total=0, processed=0, failed=0, pending=0),
        registry=_registry(retained=True),
        surfaces=_surfaces(published=7),
        runtime=_runtime(published=True),
        recovery=_recovery(WorkbenchRecoveryMode.FORBIDDEN),
        actions=(
            _action(
                WorkbenchCardActionId.OPEN_PUBLISHED_SURFACES,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Открыть опубликованные знания",
            ),
            _action(
                WorkbenchCardActionId.RESUME_PROCESSING,
                visible=False,
                enabled=False,
                label="Продолжить обработку",
                reason_code=WorkbenchCardReasonCode.RESUME_FORBIDDEN_AFTER_PUBLICATION,
            ),
        ),
        messages=(
            _message(
                WorkbenchCardReasonCode.PUBLISHED_WORKSPACE_CLEANED,
                severity=WorkbenchCardMessageSeverity.SUCCESS,
                text="Документ опубликован. Промежуточные данные очищены.",
            ),
        ),
    )

    assert card.resume_available is False
    assert card.action(WorkbenchCardActionId.RESUME_PROCESSING).enabled is False
    assert card.messages[0].default_message == (
        "Документ опубликован. Промежуточные данные очищены."
    )


def test_transient_purged_card_rejects_enabled_resume() -> None:
    with pytest.raises(ValueError, match="resume action must not be enabled"):
        WorkbenchDocumentCardView(
            document_id="document-1",
            project_id="project-1",
            file_name="faq.md",
            source_type="markdown",
            lifecycle_state=WorkbenchDocumentLifecycleState.TRANSIENT_PURGED,
            retention_state=WorkbenchDocumentRetentionState.TRANSIENT_PURGED,
            transient_purged=True,
            resume_available=False,
            status_i18n_key="knowledge.workbench.card.status.published",
            default_status_label="Опубликовано",
            status_description_i18n_key="knowledge.workbench.card.status.transientPurgedDescription",
            default_status_description="Промежуточные данные очищены.",
            timer=_timer(WorkbenchTimerMode.PUBLISHED),
            usage=_usage(),
            sections=WorkbenchSectionSummaryView(
                total=0, processed=0, failed=0, pending=0
            ),
            registry=_registry(retained=True),
            surfaces=_surfaces(published=7),
            runtime=_runtime(published=True),
            recovery=_recovery(WorkbenchRecoveryMode.FORBIDDEN),
            actions=(
                _action(
                    WorkbenchCardActionId.RESUME_PROCESSING,
                    tone=WorkbenchCardActionTone.PRIMARY,
                    label="Продолжить обработку",
                ),
            ),
            messages=(_message(WorkbenchCardReasonCode.PUBLISHED_WORKSPACE_CLEANED),),
        )


def test_error_card_requires_user_facing_error_message() -> None:
    error_message = _message(
        WorkbenchCardReasonCode.PAUSED_PROVIDER,
        severity=WorkbenchCardMessageSeverity.ERROR,
        text="Провайдер ИИ временно недоступен. Можно попробовать позже.",
    )
    error = WorkbenchCardErrorView(
        reason_code=WorkbenchCardReasonCode.PAUSED_PROVIDER,
        user_message=error_message,
        recoverable=True,
        retry_available=True,
        internal_error_ref="node-run-1",
    )

    card = WorkbenchDocumentCardView(
        document_id="document-1",
        project_id="project-1",
        file_name="faq.md",
        source_type="markdown",
        lifecycle_state=WorkbenchDocumentLifecycleState.PAUSED_PROVIDER,
        retention_state=WorkbenchDocumentRetentionState.ACTIVE_PROCESSING,
        transient_purged=False,
        resume_available=True,
        status_i18n_key="knowledge.workbench.card.status.pausedProvider",
        default_status_label="Обработка приостановлена",
        status_description_i18n_key="knowledge.workbench.card.status.pausedProviderDescription",
        default_status_description="Провайдер ИИ временно недоступен.",
        timer=_timer(),
        usage=_usage(),
        sections=_sections(),
        registry=_registry(),
        surfaces=_surfaces(),
        runtime=_runtime(),
        recovery=_recovery(WorkbenchRecoveryMode.MANUAL_ONLY),
        actions=(
            _action(
                WorkbenchCardActionId.RESUME_PROCESSING,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Продолжить обработку",
            ),
        ),
        messages=(error_message,),
        error=error,
    )

    assert card.error is error
    assert card.error.user_message.default_message == (
        "Провайдер ИИ временно недоступен. Можно попробовать позже."
    )


def test_error_card_rejects_internal_error_without_user_message() -> None:
    error_message = _message(
        WorkbenchCardReasonCode.UNKNOWN_ERROR,
        severity=WorkbenchCardMessageSeverity.INFO,
        text="Техническая ошибка.",
    )
    error = WorkbenchCardErrorView(
        reason_code=WorkbenchCardReasonCode.UNKNOWN_ERROR,
        user_message=error_message,
        recoverable=False,
        retry_available=False,
    )

    with pytest.raises(ValueError, match="error user message"):
        WorkbenchDocumentCardView(
            document_id="document-1",
            project_id="project-1",
            file_name="faq.md",
            source_type="markdown",
            lifecycle_state=WorkbenchDocumentLifecycleState.FAILED,
            retention_state=WorkbenchDocumentRetentionState.ACTIVE_PROCESSING,
            transient_purged=False,
            resume_available=False,
            status_i18n_key="knowledge.workbench.card.status.failed",
            default_status_label="Ошибка обработки",
            status_description_i18n_key="knowledge.workbench.card.status.failedDescription",
            default_status_description="Не удалось обработать документ.",
            timer=_timer(),
            usage=_usage(),
            sections=_sections(),
            registry=_registry(),
            surfaces=_surfaces(),
            runtime=_runtime(),
            recovery=_recovery(WorkbenchRecoveryMode.FORBIDDEN),
            actions=(),
            messages=(error_message,),
            error=error,
        )

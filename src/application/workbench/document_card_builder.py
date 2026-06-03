from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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


_RUNNING_PROCESSING_STATUSES = frozenset({"pending", "running", "processing"})
_PAUSED_MANUAL_STATUSES = frozenset({"paused", "pausing", "cancelled_by_user"})
_FAILED_STATUSES = frozenset({"failed", "failed_validation", "failed_fatal"})
_COMPLETED_STATUSES = frozenset({"completed", "processed"})


@dataclass(frozen=True, slots=True)
class WorkbenchDocumentCardSource:
    project_id: str
    document_id: str
    file_name: str
    source_type: str = "markdown"

    document_status: str = "uploaded"
    retention_state: str = "active_processing"
    current_processing_run_id: str | None = None

    processing_status: str | None = None
    resume_policy: str | None = None

    active_elapsed_seconds: int = 0
    wall_elapsed_seconds: int = 0
    current_active_started_at: datetime | None = None

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_call_count: int = 0

    sections_total: int = 0
    sections_processed: int = 0
    sections_failed: int = 0
    sections_pending: int = 0

    canonical_fact_count: int = 0
    final_registry_snapshot_id: str | None = None
    registry_retained: bool = False

    surface_draft_count: int = 0
    surface_ready_count: int = 0
    surface_published_count: int = 0
    surface_rejected_count: int = 0

    curation_session_id: str | None = None
    curation_session_status: str | None = None

    publication_id: str | None = None
    runtime_entry_count: int = 0

    auto_resume_scheduled_at: datetime | None = None
    last_error_kind: str | None = None
    last_user_message: str | None = None
    internal_error_ref: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("project_id", self.project_id),
            ("document_id", self.document_id),
            ("file_name", self.file_name),
            ("source_type", self.source_type),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")


def build_workbench_document_card_view(
    source: WorkbenchDocumentCardSource,
) -> WorkbenchDocumentCardView:
    lifecycle_state = _lifecycle_state(source)
    retention_state = _retention_state(source)
    transient_purged = (
        retention_state is WorkbenchDocumentRetentionState.TRANSIENT_PURGED
    )
    resume_available = _resume_available(source, transient_purged=transient_purged)

    error = _error_view(source)
    messages = _messages(source, lifecycle_state=lifecycle_state, error=error)
    timer = _timer(source, lifecycle_state=lifecycle_state)
    recovery = _recovery(source, lifecycle_state=lifecycle_state)
    actions = _actions(
        source,
        lifecycle_state=lifecycle_state,
        transient_purged=transient_purged,
        resume_available=resume_available,
    )

    status_i18n_key, default_status_label = _status_label(lifecycle_state)
    description_i18n_key, default_status_description = _status_description(
        lifecycle_state
    )

    return WorkbenchDocumentCardView(
        document_id=source.document_id,
        project_id=source.project_id,
        file_name=source.file_name,
        source_type=source.source_type,
        lifecycle_state=lifecycle_state,
        retention_state=retention_state,
        transient_purged=transient_purged,
        resume_available=resume_available,
        status_i18n_key=status_i18n_key,
        default_status_label=default_status_label,
        status_description_i18n_key=description_i18n_key,
        default_status_description=default_status_description,
        timer=timer,
        usage=WorkbenchCardUsageView(
            prompt_tokens=source.prompt_tokens,
            completion_tokens=source.completion_tokens,
            total_tokens=max(
                source.total_tokens,
                source.prompt_tokens + source.completion_tokens,
            ),
            llm_call_count=source.llm_call_count,
        ),
        sections=WorkbenchSectionSummaryView(
            total=source.sections_total,
            processed=source.sections_processed,
            failed=source.sections_failed,
            pending=source.sections_pending,
        ),
        registry=WorkbenchRegistrySummaryView(
            entry_count=source.canonical_fact_count,
            final_snapshot_id=source.final_registry_snapshot_id,
            retained=source.registry_retained,
        ),
        surfaces=WorkbenchSurfaceSummaryView(
            draft_count=source.surface_draft_count,
            ready_count=source.surface_ready_count,
            published_count=source.surface_published_count,
            rejected_count=source.surface_rejected_count,
        ),
        runtime=WorkbenchRuntimeSummaryView(
            publication_id=source.publication_id,
            runtime_entry_count=source.runtime_entry_count,
        ),
        recovery=recovery,
        actions=actions,
        messages=messages,
        error=error,
        metadata={
            "current_processing_run_id": source.current_processing_run_id,
            "curation_session_id": source.curation_session_id,
            "curation_session_status": source.curation_session_status,
        },
    )


def _lifecycle_state(
    source: WorkbenchDocumentCardSource,
) -> WorkbenchDocumentLifecycleState:
    retention_state = source.retention_state.strip().lower()
    document_status = source.document_status.strip().lower()
    processing_status = (source.processing_status or "").strip().lower()
    error_kind = (source.last_error_kind or "").strip().lower()
    curation_status = (source.curation_session_status or "").strip().lower()

    if retention_state == WorkbenchDocumentRetentionState.TRANSIENT_PURGED.value:
        return WorkbenchDocumentLifecycleState.TRANSIENT_PURGED
    if document_status == "published":
        return WorkbenchDocumentLifecycleState.PUBLISHED
    if document_status == "deleted":
        return WorkbenchDocumentLifecycleState.DELETED

    if source.auto_resume_scheduled_at is not None:
        return WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED

    if processing_status in _RUNNING_PROCESSING_STATUSES:
        return WorkbenchDocumentLifecycleState.PROCESSING

    if processing_status in _PAUSED_MANUAL_STATUSES:
        return WorkbenchDocumentLifecycleState.PAUSED_MANUAL

    if error_kind in {"groq_daily_limit", "groq_rate_limit", "quota_exhausted"}:
        return WorkbenchDocumentLifecycleState.PAUSED_QUOTA

    if error_kind in {"provider_error", "provider_rate_limit", "llm_provider_error"}:
        return WorkbenchDocumentLifecycleState.PAUSED_PROVIDER

    if error_kind in {"render_shutdown", "server_interrupted", "worker_shutdown"}:
        return WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED

    if processing_status in _FAILED_STATUSES:
        return WorkbenchDocumentLifecycleState.FAILED

    if curation_status == "publish_pending":
        return WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION

    if source.curation_session_id or source.surface_ready_count > 0:
        return WorkbenchDocumentLifecycleState.READY_FOR_CURATION

    if processing_status in _COMPLETED_STATUSES or document_status == "processed":
        return WorkbenchDocumentLifecycleState.READY_FOR_CURATION

    if source.sections_total > 0:
        return WorkbenchDocumentLifecycleState.SECTIONED

    return WorkbenchDocumentLifecycleState.UPLOADED


def _retention_state(
    source: WorkbenchDocumentCardSource,
) -> WorkbenchDocumentRetentionState:
    normalized = source.retention_state.strip().lower()
    try:
        return WorkbenchDocumentRetentionState(normalized)
    except ValueError:
        return WorkbenchDocumentRetentionState.ACTIVE_PROCESSING


def _resume_available(
    source: WorkbenchDocumentCardSource,
    *,
    transient_purged: bool,
) -> bool:
    if transient_purged:
        return False
    if source.current_processing_run_id is None:
        return False
    if (source.resume_policy or "").strip().lower() == "forbidden":
        return False
    if source.document_status.strip().lower() in {"published", "deleted"}:
        return False

    processing_status = (source.processing_status or "").strip().lower()
    if processing_status in _RUNNING_PROCESSING_STATUSES:
        return False

    return (source.resume_policy or "").strip().lower() in {
        "manual_only",
        "auto_allowed",
    }


def _timer(
    source: WorkbenchDocumentCardSource,
    *,
    lifecycle_state: WorkbenchDocumentLifecycleState,
) -> WorkbenchCardTimerView:
    if lifecycle_state is WorkbenchDocumentLifecycleState.PROCESSING:
        mode = WorkbenchTimerMode.RUNNING
        started_at = source.current_active_started_at
        label_key = "knowledge.workbench.card.timer.running"
        label = "Идёт обработка"
    elif lifecycle_state in {
        WorkbenchDocumentLifecycleState.READY_FOR_CURATION,
        WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION,
    }:
        mode = WorkbenchTimerMode.COMPLETED
        started_at = None
        label_key = "knowledge.workbench.card.timer.completed"
        label = "Обработка завершена"
    elif lifecycle_state in {
        WorkbenchDocumentLifecycleState.PUBLISHED,
        WorkbenchDocumentLifecycleState.TRANSIENT_PURGED,
    }:
        mode = WorkbenchTimerMode.PUBLISHED
        started_at = None
        label_key = "knowledge.workbench.card.timer.published"
        label = "Опубликовано"
    elif lifecycle_state in {
        WorkbenchDocumentLifecycleState.PAUSED_MANUAL,
        WorkbenchDocumentLifecycleState.PAUSED_QUOTA,
        WorkbenchDocumentLifecycleState.PAUSED_PROVIDER,
        WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED,
        WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED,
    }:
        mode = WorkbenchTimerMode.PAUSED
        started_at = None
        label_key = "knowledge.workbench.card.timer.paused"
        label = "Обработка на паузе"
    else:
        mode = WorkbenchTimerMode.STOPPED
        started_at = None
        label_key = "knowledge.workbench.card.timer.stopped"
        label = "Таймер остановлен"

    return WorkbenchCardTimerView(
        mode=mode,
        active_elapsed_seconds=source.active_elapsed_seconds,
        wall_elapsed_seconds=max(
            source.wall_elapsed_seconds,
            source.active_elapsed_seconds,
        ),
        current_active_started_at=started_at,
        i18n_key=label_key,
        default_label=label,
    )


def _recovery(
    source: WorkbenchDocumentCardSource,
    *,
    lifecycle_state: WorkbenchDocumentLifecycleState,
) -> WorkbenchRecoveryView:
    if lifecycle_state is WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED:
        return WorkbenchRecoveryView(
            mode=WorkbenchRecoveryMode.SCHEDULED_AUTO_RESUME,
            scheduled_at=source.auto_resume_scheduled_at,
            can_cancel_scheduled_resume=True,
            reason_code=WorkbenchCardReasonCode.AUTO_RESUME_SCHEDULED,
            i18n_key="knowledge.workbench.card.recovery.autoScheduled",
            default_message="Автопродолжение запланировано.",
        )

    if lifecycle_state in {
        WorkbenchDocumentLifecycleState.PAUSED_MANUAL,
        WorkbenchDocumentLifecycleState.PAUSED_QUOTA,
        WorkbenchDocumentLifecycleState.PAUSED_PROVIDER,
        WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED,
    }:
        return WorkbenchRecoveryView(
            mode=WorkbenchRecoveryMode.MANUAL_ONLY,
            scheduled_at=None,
            can_cancel_scheduled_resume=False,
            reason_code=WorkbenchCardReasonCode.MANUAL_RESUME_AVAILABLE,
            i18n_key="knowledge.workbench.card.recovery.manualOnly",
            default_message="Можно продолжить обработку вручную.",
        )

    if lifecycle_state in {
        WorkbenchDocumentLifecycleState.PUBLISHED,
        WorkbenchDocumentLifecycleState.TRANSIENT_PURGED,
        WorkbenchDocumentLifecycleState.DELETED,
    }:
        return WorkbenchRecoveryView(
            mode=WorkbenchRecoveryMode.FORBIDDEN,
            scheduled_at=None,
            can_cancel_scheduled_resume=False,
            reason_code=WorkbenchCardReasonCode.RESUME_FORBIDDEN_AFTER_PUBLICATION,
            i18n_key="knowledge.workbench.card.recovery.forbidden",
            default_message="Продолжение обработки недоступно.",
        )

    return WorkbenchRecoveryView(
        mode=WorkbenchRecoveryMode.NONE,
        scheduled_at=None,
        can_cancel_scheduled_resume=False,
        reason_code=WorkbenchCardReasonCode.RUNNING,
        i18n_key="knowledge.workbench.card.recovery.none",
        default_message="Автопродолжение не запланировано.",
    )


def _actions(
    source: WorkbenchDocumentCardSource,
    *,
    lifecycle_state: WorkbenchDocumentLifecycleState,
    transient_purged: bool,
    resume_available: bool,
) -> tuple[WorkbenchCardActionView, ...]:
    actions: list[WorkbenchCardActionView] = []

    if lifecycle_state is WorkbenchDocumentLifecycleState.PROCESSING:
        actions.append(
            _action(
                WorkbenchCardActionId.CANCEL_PROCESSING,
                tone=WorkbenchCardActionTone.WARNING,
                label="Остановить обработку",
                confirmation="Остановить обработку документа?",
            )
        )

    if lifecycle_state is WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED:
        actions.append(
            _action(
                WorkbenchCardActionId.RESUME_PROCESSING,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Продолжить сейчас",
                enabled=resume_available,
                disabled_reason=WorkbenchCardReasonCode.MANUAL_RESUME_AVAILABLE
                if not resume_available
                else None,
            )
        )
        actions.append(
            _action(
                WorkbenchCardActionId.CANCEL_SCHEDULED_RECOVERY,
                label="Отменить автопродолжение",
                confirmation="Отменить запланированное автопродолжение?",
            )
        )

    if lifecycle_state in {
        WorkbenchDocumentLifecycleState.PAUSED_MANUAL,
        WorkbenchDocumentLifecycleState.PAUSED_QUOTA,
        WorkbenchDocumentLifecycleState.PAUSED_PROVIDER,
        WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED,
        WorkbenchDocumentLifecycleState.FAILED,
    }:
        actions.append(
            _action(
                WorkbenchCardActionId.RESUME_PROCESSING,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Продолжить обработку",
                enabled=resume_available,
                disabled_reason=WorkbenchCardReasonCode.MANUAL_RESUME_AVAILABLE
                if not resume_available
                else None,
            )
        )

    if lifecycle_state in {
        WorkbenchDocumentLifecycleState.READY_FOR_CURATION,
        WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION,
    }:
        actions.append(
            _action(
                WorkbenchCardActionId.OPEN_CURATION,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Открыть курацию",
            )
        )

    if lifecycle_state is WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION:
        actions.append(
            _action(
                WorkbenchCardActionId.PUBLISH_READY,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Опубликовать готовые",
                confirmation="Опубликовать проверенные карточки знаний?",
            )
        )

    if lifecycle_state in {
        WorkbenchDocumentLifecycleState.PUBLISHED,
        WorkbenchDocumentLifecycleState.TRANSIENT_PURGED,
    }:
        actions.append(
            _action(
                WorkbenchCardActionId.OPEN_PUBLISHED_SURFACES,
                tone=WorkbenchCardActionTone.PRIMARY,
                label="Открыть опубликованные знания",
            )
        )

    if not transient_purged and lifecycle_state not in {
        WorkbenchDocumentLifecycleState.DELETED,
    }:
        actions.append(
            _action(
                WorkbenchCardActionId.OPEN_WORKBENCH,
                label="Открыть Workbench",
            )
        )

    if transient_purged:
        actions.append(
            _action(
                WorkbenchCardActionId.RESUME_PROCESSING,
                visible=False,
                enabled=False,
                label="Продолжить обработку",
                disabled_reason=WorkbenchCardReasonCode.RESUME_FORBIDDEN_AFTER_PUBLICATION,
            )
        )

    if lifecycle_state is not WorkbenchDocumentLifecycleState.DELETED:
        actions.append(
            _action(
                WorkbenchCardActionId.DELETE_DOCUMENT,
                tone=WorkbenchCardActionTone.DANGER,
                label="Удалить документ",
                confirmation=_delete_confirmation(
                    source, transient_purged=transient_purged
                ),
            )
        )

    return tuple(actions)


def _action(
    action_id: WorkbenchCardActionId,
    *,
    label: str,
    visible: bool = True,
    enabled: bool = True,
    tone: WorkbenchCardActionTone = WorkbenchCardActionTone.SECONDARY,
    confirmation: str | None = None,
    disabled_reason: WorkbenchCardReasonCode | None = None,
) -> WorkbenchCardActionView:
    return WorkbenchCardActionView(
        action_id=action_id,
        visible=visible,
        enabled=enabled,
        tone=tone,
        i18n_key=f"knowledge.workbench.card.actions.{action_id.value}",
        default_label=label,
        reason_code=disabled_reason,
        confirmation_i18n_key=f"knowledge.workbench.card.confirmations.{action_id.value}"
        if confirmation
        else None,
        default_confirmation=confirmation,
    )


def _delete_confirmation(
    source: WorkbenchDocumentCardSource,
    *,
    transient_purged: bool,
) -> str:
    if transient_purged or source.publication_id:
        return "Удалить опубликованные знания этого документа из проекта?"
    if source.current_processing_run_id:
        return "Остановить обработку и удалить рабочие данные документа?"
    return "Удалить документ из базы знаний проекта?"


def _messages(
    source: WorkbenchDocumentCardSource,
    *,
    lifecycle_state: WorkbenchDocumentLifecycleState,
    error: WorkbenchCardErrorView | None,
) -> tuple[WorkbenchCardUserMessage, ...]:
    messages: list[WorkbenchCardUserMessage] = []

    if lifecycle_state is WorkbenchDocumentLifecycleState.PROCESSING:
        messages.append(
            _message(
                WorkbenchCardReasonCode.RUNNING,
                WorkbenchCardMessageSeverity.INFO,
                "Документ обрабатывается. Можно остановить обработку без удаления документа.",
            )
        )
    elif lifecycle_state is WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED:
        messages.append(
            _message(
                WorkbenchCardReasonCode.AUTO_RESUME_SCHEDULED,
                WorkbenchCardMessageSeverity.WARNING,
                "Обработка приостановлена. Автопродолжение уже запланировано.",
            )
        )
    elif lifecycle_state in {
        WorkbenchDocumentLifecycleState.PAUSED_MANUAL,
        WorkbenchDocumentLifecycleState.PAUSED_QUOTA,
        WorkbenchDocumentLifecycleState.PAUSED_PROVIDER,
        WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED,
    }:
        messages.append(
            _message(
                _pause_reason_code(lifecycle_state),
                WorkbenchCardMessageSeverity.WARNING,
                source.last_user_message
                or "Обработка приостановлена. Можно продолжить вручную.",
            )
        )
    elif lifecycle_state is WorkbenchDocumentLifecycleState.READY_FOR_CURATION:
        messages.append(
            _message(
                WorkbenchCardReasonCode.READY_FOR_CURATION,
                WorkbenchCardMessageSeverity.SUCCESS,
                "Черновики карточек готовы. Проверьте их в курации.",
            )
        )
    elif lifecycle_state is WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION:
        messages.append(
            _message(
                WorkbenchCardReasonCode.READY_FOR_PUBLICATION,
                WorkbenchCardMessageSeverity.SUCCESS,
                "Карточки проверены и готовы к публикации.",
            )
        )
    elif lifecycle_state is WorkbenchDocumentLifecycleState.TRANSIENT_PURGED:
        messages.append(
            _message(
                WorkbenchCardReasonCode.PUBLISHED_WORKSPACE_CLEANED,
                WorkbenchCardMessageSeverity.SUCCESS,
                "Документ опубликован. Промежуточные данные очищены.",
            )
        )
    elif lifecycle_state is WorkbenchDocumentLifecycleState.DELETED:
        messages.append(
            _message(
                WorkbenchCardReasonCode.DOCUMENT_DELETED,
                WorkbenchCardMessageSeverity.INFO,
                "Документ удалён.",
            )
        )

    if error is not None and not any(
        message.severity is WorkbenchCardMessageSeverity.ERROR for message in messages
    ):
        messages.append(error.user_message)

    return tuple(messages)


def _error_view(source: WorkbenchDocumentCardSource) -> WorkbenchCardErrorView | None:
    if not source.last_error_kind:
        return None

    reason_code = _error_reason_code(source.last_error_kind)
    user_text = source.last_user_message or _default_error_message(reason_code)
    user_message = _message(
        reason_code,
        WorkbenchCardMessageSeverity.ERROR,
        user_text,
        debug_ref=source.internal_error_ref,
    )

    recoverable = reason_code in {
        WorkbenchCardReasonCode.PAUSED_API_LIMIT,
        WorkbenchCardReasonCode.PAUSED_PROVIDER,
        WorkbenchCardReasonCode.PAUSED_SERVER_INTERRUPTED,
    }
    return WorkbenchCardErrorView(
        reason_code=reason_code,
        user_message=user_message,
        recoverable=recoverable,
        retry_available=recoverable and source.current_processing_run_id is not None,
        internal_error_ref=source.internal_error_ref,
    )


def _message(
    code: WorkbenchCardReasonCode,
    severity: WorkbenchCardMessageSeverity,
    text: str,
    *,
    debug_ref: str | None = None,
) -> WorkbenchCardUserMessage:
    return WorkbenchCardUserMessage(
        code=code,
        severity=severity,
        i18n_key=f"knowledge.workbench.card.messages.{code.value}",
        default_message=text,
        debug_ref=debug_ref,
    )


def _pause_reason_code(
    lifecycle_state: WorkbenchDocumentLifecycleState,
) -> WorkbenchCardReasonCode:
    if lifecycle_state is WorkbenchDocumentLifecycleState.PAUSED_QUOTA:
        return WorkbenchCardReasonCode.PAUSED_API_LIMIT
    if lifecycle_state is WorkbenchDocumentLifecycleState.PAUSED_PROVIDER:
        return WorkbenchCardReasonCode.PAUSED_PROVIDER
    if lifecycle_state is WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED:
        return WorkbenchCardReasonCode.PAUSED_SERVER_INTERRUPTED
    return WorkbenchCardReasonCode.PAUSED_BY_USER


def _error_reason_code(error_kind: str) -> WorkbenchCardReasonCode:
    normalized = error_kind.strip().lower()
    if normalized in {"groq_daily_limit", "groq_rate_limit", "quota_exhausted"}:
        return WorkbenchCardReasonCode.PAUSED_API_LIMIT
    if normalized in {"provider_error", "provider_rate_limit", "llm_provider_error"}:
        return WorkbenchCardReasonCode.PAUSED_PROVIDER
    if normalized in {"render_shutdown", "server_interrupted", "worker_shutdown"}:
        return WorkbenchCardReasonCode.PAUSED_SERVER_INTERRUPTED
    if normalized in {"failed", "failed_validation", "failed_fatal"}:
        return WorkbenchCardReasonCode.PROCESSING_FAILED
    return WorkbenchCardReasonCode.UNKNOWN_ERROR


def _default_error_message(reason_code: WorkbenchCardReasonCode) -> str:
    if reason_code is WorkbenchCardReasonCode.PAUSED_API_LIMIT:
        return "Лимит ИИ временно исчерпан. Обработку можно продолжить позже."
    if reason_code is WorkbenchCardReasonCode.PAUSED_PROVIDER:
        return "Провайдер ИИ временно недоступен. Можно попробовать позже."
    if reason_code is WorkbenchCardReasonCode.PAUSED_SERVER_INTERRUPTED:
        return "Обработка остановилась из-за перезапуска сервера. Её можно продолжить."
    if reason_code is WorkbenchCardReasonCode.PROCESSING_FAILED:
        return "Не удалось обработать документ. Проверьте файл или попробуйте снова."
    return "Произошла ошибка обработки. Подробности сохранены для диагностики."


def _status_label(
    lifecycle_state: WorkbenchDocumentLifecycleState,
) -> tuple[str, str]:
    labels = {
        WorkbenchDocumentLifecycleState.UPLOADED: ("uploaded", "Загружен"),
        WorkbenchDocumentLifecycleState.SECTIONED: ("sectioned", "Разбит на секции"),
        WorkbenchDocumentLifecycleState.PROCESSING: ("processing", "Обрабатывается"),
        WorkbenchDocumentLifecycleState.PAUSED_MANUAL: ("pausedManual", "На паузе"),
        WorkbenchDocumentLifecycleState.PAUSED_QUOTA: (
            "pausedQuota",
            "Приостановлено: лимит ИИ",
        ),
        WorkbenchDocumentLifecycleState.PAUSED_PROVIDER: (
            "pausedProvider",
            "Приостановлено: провайдер ИИ",
        ),
        WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED: (
            "pausedServerInterrupted",
            "Приостановлено: сервер",
        ),
        WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED: (
            "autoRecoveryScheduled",
            "Автопродолжение запланировано",
        ),
        WorkbenchDocumentLifecycleState.CANCELLED: ("cancelled", "Остановлено"),
        WorkbenchDocumentLifecycleState.FAILED: ("failed", "Ошибка обработки"),
        WorkbenchDocumentLifecycleState.READY_FOR_CURATION: (
            "readyForCuration",
            "Готово к курации",
        ),
        WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION: (
            "readyForPublication",
            "Готово к публикации",
        ),
        WorkbenchDocumentLifecycleState.PUBLISHING: ("publishing", "Публикуется"),
        WorkbenchDocumentLifecycleState.PUBLISHED: ("published", "Опубликовано"),
        WorkbenchDocumentLifecycleState.TRANSIENT_PURGED: (
            "transientPurged",
            "Опубликовано",
        ),
        WorkbenchDocumentLifecycleState.DELETED: ("deleted", "Удалено"),
    }
    suffix, fallback = labels[lifecycle_state]
    return f"knowledge.workbench.card.status.{suffix}", fallback


def _status_description(
    lifecycle_state: WorkbenchDocumentLifecycleState,
) -> tuple[str, str]:
    descriptions = {
        WorkbenchDocumentLifecycleState.UPLOADED: "Документ принят и ждёт обработки.",
        WorkbenchDocumentLifecycleState.SECTIONED: "Документ разбит на рабочие секции.",
        WorkbenchDocumentLifecycleState.PROCESSING: "ИИ собирает карточки знаний из секций.",
        WorkbenchDocumentLifecycleState.PAUSED_MANUAL: "Обработка остановлена вручную.",
        WorkbenchDocumentLifecycleState.PAUSED_QUOTA: (
            "Обработка ждёт восстановления лимитов ИИ."
        ),
        WorkbenchDocumentLifecycleState.PAUSED_PROVIDER: (
            "Обработка ждёт доступности провайдера ИИ."
        ),
        WorkbenchDocumentLifecycleState.PAUSED_SERVER_INTERRUPTED: (
            "Обработка была остановлена сервером и может быть продолжена."
        ),
        WorkbenchDocumentLifecycleState.AUTO_RECOVERY_SCHEDULED: (
            "Система попробует продолжить обработку автоматически."
        ),
        WorkbenchDocumentLifecycleState.CANCELLED: "Обработка остановлена.",
        WorkbenchDocumentLifecycleState.FAILED: "Документ не удалось обработать.",
        WorkbenchDocumentLifecycleState.READY_FOR_CURATION: (
            "Проверьте и отредактируйте карточки перед публикацией."
        ),
        WorkbenchDocumentLifecycleState.READY_FOR_PUBLICATION: (
            "Проверенные карточки можно опубликовать в ответы бота."
        ),
        WorkbenchDocumentLifecycleState.PUBLISHING: "Карточки публикуются в runtime.",
        WorkbenchDocumentLifecycleState.PUBLISHED: "Карточки доступны для ответов бота.",
        WorkbenchDocumentLifecycleState.TRANSIENT_PURGED: (
            "Карточки опубликованы, промежуточные данные обработки очищены."
        ),
        WorkbenchDocumentLifecycleState.DELETED: "Документ удалён из Workbench.",
    }
    suffix = _status_label(lifecycle_state)[0].split(".")[-1]
    return (
        f"knowledge.workbench.card.status.{suffix}Description",
        descriptions[lifecycle_state],
    )


__all__ = [
    "WorkbenchDocumentCardSource",
    "build_workbench_document_card_view",
]

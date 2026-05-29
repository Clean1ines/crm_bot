from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

KnowledgeDocumentLifecycleState: TypeAlias = Literal[
    "uploaded",
    "queued",
    "processing",
    "paused_quota",
    "paused_provider",
    "interrupted",
    "cancelled_by_user",
    "failed_validation",
    "failed_fatal",
    "completed",
    "awaiting_publication",
    "published",
    "deleted",
]

KnowledgeDocumentStopReason: TypeAlias = Literal[
    "none",
    "user_cancelled",
    "quota_exhausted",
    "provider_fallback_exhausted",
    "input_too_large",
    "worker_interrupted",
    "validation_failed",
    "fatal_error",
]

KnowledgeDocumentResumePolicy: TypeAlias = Literal[
    "auto_allowed",
    "manual_only",
    "forbidden",
    "not_needed",
]

KnowledgeDocumentLifecycleTrigger: TypeAlias = Literal[
    "normal_upload",
    "explicit_user_resume",
    "worker_recovery",
    "quota_recovery",
    "stale_job_recovery",
    "manual_cancel",
    "clear_project",
    "delete_document",
]

STATE_UPLOADED: KnowledgeDocumentLifecycleState = "uploaded"
STATE_QUEUED: KnowledgeDocumentLifecycleState = "queued"
STATE_PROCESSING: KnowledgeDocumentLifecycleState = "processing"
STATE_PAUSED_QUOTA: KnowledgeDocumentLifecycleState = "paused_quota"
STATE_PAUSED_PROVIDER: KnowledgeDocumentLifecycleState = "paused_provider"
STATE_INTERRUPTED: KnowledgeDocumentLifecycleState = "interrupted"
STATE_CANCELLED_BY_USER: KnowledgeDocumentLifecycleState = "cancelled_by_user"
STATE_FAILED_VALIDATION: KnowledgeDocumentLifecycleState = "failed_validation"
STATE_FAILED_FATAL: KnowledgeDocumentLifecycleState = "failed_fatal"
STATE_COMPLETED: KnowledgeDocumentLifecycleState = "completed"
STATE_AWAITING_PUBLICATION: KnowledgeDocumentLifecycleState = "awaiting_publication"
STATE_PUBLISHED: KnowledgeDocumentLifecycleState = "published"
STATE_DELETED: KnowledgeDocumentLifecycleState = "deleted"

STOP_REASON_NONE: KnowledgeDocumentStopReason = "none"
STOP_REASON_USER_CANCELLED: KnowledgeDocumentStopReason = "user_cancelled"
STOP_REASON_QUOTA_EXHAUSTED: KnowledgeDocumentStopReason = "quota_exhausted"
STOP_REASON_PROVIDER_FALLBACK_EXHAUSTED: KnowledgeDocumentStopReason = (
    "provider_fallback_exhausted"
)
STOP_REASON_INPUT_TOO_LARGE: KnowledgeDocumentStopReason = "input_too_large"
STOP_REASON_WORKER_INTERRUPTED: KnowledgeDocumentStopReason = "worker_interrupted"
STOP_REASON_VALIDATION_FAILED: KnowledgeDocumentStopReason = "validation_failed"
STOP_REASON_FATAL_ERROR: KnowledgeDocumentStopReason = "fatal_error"

RESUME_POLICY_AUTO_ALLOWED: KnowledgeDocumentResumePolicy = "auto_allowed"
RESUME_POLICY_MANUAL_ONLY: KnowledgeDocumentResumePolicy = "manual_only"
RESUME_POLICY_FORBIDDEN: KnowledgeDocumentResumePolicy = "forbidden"
RESUME_POLICY_NOT_NEEDED: KnowledgeDocumentResumePolicy = "not_needed"

TRIGGER_NORMAL_UPLOAD: KnowledgeDocumentLifecycleTrigger = "normal_upload"
TRIGGER_EXPLICIT_USER_RESUME: KnowledgeDocumentLifecycleTrigger = "explicit_user_resume"
TRIGGER_WORKER_RECOVERY: KnowledgeDocumentLifecycleTrigger = "worker_recovery"
TRIGGER_QUOTA_RECOVERY: KnowledgeDocumentLifecycleTrigger = "quota_recovery"
TRIGGER_STALE_JOB_RECOVERY: KnowledgeDocumentLifecycleTrigger = "stale_job_recovery"
TRIGGER_MANUAL_CANCEL: KnowledgeDocumentLifecycleTrigger = "manual_cancel"
TRIGGER_CLEAR_PROJECT: KnowledgeDocumentLifecycleTrigger = "clear_project"
TRIGGER_DELETE_DOCUMENT: KnowledgeDocumentLifecycleTrigger = "delete_document"

LEGACY_USER_CANCELLED_MESSAGE = "Остановлено пользователем"
PROCESSING_PAUSED_QUOTA_STATUS = "processing_paused_quota"
NEEDS_RETRY_LATER_STATUS = "needs_retry_later"
NON_RETRYABLE_INPUT_TOO_LARGE_STATUS = "non_retryable_input_too_large"

_LEGACY_USER_CANCELLED_EQUIVALENTS: frozenset[str] = frozenset(
    {
        LEGACY_USER_CANCELLED_MESSAGE.lower(),
        "knowledge document processing was cancelled",
    }
)

_PROCESSING_STATUSES: frozenset[str] = frozenset({"processing", "pending", "queued"})
_COMPLETED_STATUSES: frozenset[str] = frozenset(
    {"processed", "completed", "complete", "published"}
)
_FAILED_STATUSES: frozenset[str] = frozenset({"error", "failed", "failure"})
_DELETED_STATUSES: frozenset[str] = frozenset({"deleted"})
_VALIDATION_FAILED_STATUSES: frozenset[str] = frozenset(
    {"failed_validation", "validation_failed"}
)
_RECOVERABLE_AUTO_RESUME_KEYS: frozenset[str] = frozenset(
    {
        "can_retry_later",
        "safe_to_auto_resume",
        "auto_resume_allowed",
    }
)


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentLifecycleAction:
    id: str
    label: str
    kind: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentLifecycleDecision:
    state: KnowledgeDocumentLifecycleState
    stop_reason: KnowledgeDocumentStopReason
    resume_policy: KnowledgeDocumentResumePolicy
    is_processing: bool
    is_terminal: bool
    is_recoverable: bool
    can_auto_resume: bool
    can_manual_resume: bool
    should_show_resume_action: bool
    should_show_cancel_action: bool
    status_message: str
    actions: tuple[KnowledgeDocumentLifecycleAction, ...]


def resolve_knowledge_document_lifecycle(
    *,
    document_status: str,
    preprocessing_status: str | None,
    preprocessing_error: str | None,
    preprocessing_metrics: Mapping[str, object] | None,
    chunk_count: int = 0,
    structured_entries: int = 0,
    raw_candidate_count: int = 0,
    published_answer_count: int = 0,
    batch_failed_count: int = 0,
) -> KnowledgeDocumentLifecycleDecision:
    """Resolve a knowledge-document lifecycle decision from persisted state.

    This function is deliberately pure domain logic: it has no application,
    infrastructure, database, queue, framework, or LLM imports. It only
    normalizes legacy lifecycle signals into a first-class decision object.
    """

    metrics = dict(preprocessing_metrics or {})
    status_values = _status_values(
        document_status=document_status,
        preprocessing_status=preprocessing_status,
        preprocessing_error=preprocessing_error,
        metrics=metrics,
    )

    if _has_legacy_user_cancelled_signal(status_values):
        return _decision(
            state=STATE_CANCELLED_BY_USER,
            stop_reason=STOP_REASON_USER_CANCELLED,
            resume_policy=RESUME_POLICY_MANUAL_ONLY,
            is_recoverable=True,
            status_message=(
                "Обработка остановлена пользователем. Продолжение возможно "
                "только явным действием пользователя."
            ),
        )

    if _has_status(status_values, PROCESSING_PAUSED_QUOTA_STATUS):
        return _decision(
            state=STATE_PAUSED_QUOTA,
            stop_reason=STOP_REASON_QUOTA_EXHAUSTED,
            resume_policy=RESUME_POLICY_AUTO_ALLOWED,
            is_recoverable=True,
            status_message=(
                "Дневной лимит LLM исчерпан; сохранённый прогресс можно "
                "продолжить после восстановления лимита."
            ),
            include_retry_later_action=True,
        )

    if _has_status(status_values, NEEDS_RETRY_LATER_STATUS):
        return _decision(
            state=STATE_PAUSED_PROVIDER,
            stop_reason=STOP_REASON_PROVIDER_FALLBACK_EXHAUSTED,
            resume_policy=RESUME_POLICY_AUTO_ALLOWED,
            is_recoverable=True,
            status_message=(
                "Доступные provider fallback-маршруты исчерпаны; сохранённый "
                "прогресс можно повторить позже."
            ),
            include_retry_later_action=True,
        )

    if _has_status(status_values, NON_RETRYABLE_INPUT_TOO_LARGE_STATUS):
        return _decision(
            state=STATE_FAILED_VALIDATION,
            stop_reason=STOP_REASON_INPUT_TOO_LARGE,
            resume_policy=RESUME_POLICY_FORBIDDEN,
            is_recoverable=False,
            status_message=(
                "Документ слишком большой для доступных LLM-маршрутов; "
                "автоматическое или ручное продолжение запрещено."
            ),
        )

    if _has_any_status(status_values, _DELETED_STATUSES):
        return _decision(
            state=STATE_DELETED,
            stop_reason=STOP_REASON_NONE,
            resume_policy=RESUME_POLICY_FORBIDDEN,
            is_recoverable=False,
            status_message="Документ удалён.",
        )

    if _has_any_status(status_values, _VALIDATION_FAILED_STATUSES):
        return _decision(
            state=STATE_FAILED_VALIDATION,
            stop_reason=STOP_REASON_VALIDATION_FAILED,
            resume_policy=RESUME_POLICY_FORBIDDEN,
            is_recoverable=False,
            status_message="Документ не прошёл валидацию и не может быть продолжен.",
        )

    if _has_any_status(status_values, _PROCESSING_STATUSES):
        return _decision(
            state=STATE_PROCESSING,
            stop_reason=STOP_REASON_NONE,
            resume_policy=RESUME_POLICY_FORBIDDEN,
            is_recoverable=False,
            status_message="Документ сейчас обрабатывается.",
            include_publish_ready_action=raw_candidate_count > published_answer_count,
        )

    if _has_any_status(status_values, _COMPLETED_STATUSES):
        if (
            _positive(published_answer_count)
            or _normalise(document_status) == STATE_PUBLISHED
        ):
            return _decision(
                state=STATE_PUBLISHED,
                stop_reason=STOP_REASON_NONE,
                resume_policy=RESUME_POLICY_NOT_NEEDED,
                is_recoverable=False,
                status_message="Документ обработан и опубликован в базе знаний.",
            )
        if _positive(structured_entries):
            return _decision(
                state=STATE_COMPLETED,
                stop_reason=STOP_REASON_NONE,
                resume_policy=RESUME_POLICY_NOT_NEEDED,
                is_recoverable=False,
                status_message="Документ обработан, структурированные записи готовы.",
            )
        if _positive(raw_candidate_count):
            return _decision(
                state=STATE_AWAITING_PUBLICATION,
                stop_reason=STOP_REASON_NONE,
                resume_policy=RESUME_POLICY_NOT_NEEDED,
                is_recoverable=False,
                status_message="Документ обработан и ожидает публикации найденных ответов.",
                include_publish_ready_action=True,
            )
        return _decision(
            state=STATE_COMPLETED,
            stop_reason=STOP_REASON_NONE,
            resume_policy=RESUME_POLICY_NOT_NEEDED,
            is_recoverable=False,
            status_message="Документ обработан.",
        )

    if _positive(batch_failed_count):
        return _decision(
            state=STATE_INTERRUPTED,
            stop_reason=STOP_REASON_WORKER_INTERRUPTED,
            resume_policy=RESUME_POLICY_AUTO_ALLOWED,
            is_recoverable=True,
            status_message="Есть проблемные batch-части, которые можно повторить.",
            include_retry_failed_batches_action=True,
            include_publish_ready_action=raw_candidate_count > published_answer_count,
        )

    if _has_any_status(status_values, _FAILED_STATUSES):
        if _has_explicit_safe_auto_recovery(metrics):
            return _decision(
                state=STATE_INTERRUPTED,
                stop_reason=STOP_REASON_WORKER_INTERRUPTED,
                resume_policy=RESUME_POLICY_AUTO_ALLOWED,
                is_recoverable=True,
                status_message=(
                    "Обработка была прервана, но metrics явно разрешают "
                    "безопасное автоматическое продолжение."
                ),
                include_retry_later_action=True,
                include_retry_failed_batches_action=_positive(batch_failed_count),
                include_publish_ready_action=raw_candidate_count
                > published_answer_count,
            )
        return _decision(
            state=STATE_FAILED_FATAL,
            stop_reason=STOP_REASON_FATAL_ERROR,
            resume_policy=RESUME_POLICY_FORBIDDEN,
            is_recoverable=False,
            status_message="Обработка завершилась фатальной ошибкой.",
        )

    if _positive(raw_candidate_count) and raw_candidate_count > max(
        structured_entries,
        published_answer_count,
    ):
        return _decision(
            state=STATE_AWAITING_PUBLICATION,
            stop_reason=STOP_REASON_NONE,
            resume_policy=RESUME_POLICY_NOT_NEEDED,
            is_recoverable=False,
            status_message="Найденные ответы ожидают публикации.",
            include_publish_ready_action=True,
        )

    if _positive(chunk_count) or _normalise(document_status) == STATE_UPLOADED:
        return _decision(
            state=STATE_UPLOADED,
            stop_reason=STOP_REASON_NONE,
            resume_policy=RESUME_POLICY_FORBIDDEN,
            is_recoverable=False,
            status_message="Документ загружен и ожидает обработки.",
        )

    return _decision(
        state=STATE_QUEUED,
        stop_reason=STOP_REASON_NONE,
        resume_policy=RESUME_POLICY_FORBIDDEN,
        is_recoverable=False,
        status_message="Документ ожидает постановки в обработку.",
    )


def _decision(
    *,
    state: KnowledgeDocumentLifecycleState,
    stop_reason: KnowledgeDocumentStopReason,
    resume_policy: KnowledgeDocumentResumePolicy,
    is_recoverable: bool,
    status_message: str,
    include_retry_later_action: bool = False,
    include_retry_failed_batches_action: bool = False,
    include_publish_ready_action: bool = False,
) -> KnowledgeDocumentLifecycleDecision:
    is_processing = state in {STATE_QUEUED, STATE_PROCESSING}
    is_terminal = state in {
        STATE_CANCELLED_BY_USER,
        STATE_FAILED_VALIDATION,
        STATE_FAILED_FATAL,
        STATE_COMPLETED,
        STATE_PUBLISHED,
        STATE_DELETED,
    }
    can_auto_resume = resume_policy == RESUME_POLICY_AUTO_ALLOWED
    can_manual_resume = resume_policy == RESUME_POLICY_MANUAL_ONLY
    should_show_resume_action = can_manual_resume
    should_show_cancel_action = is_processing

    actions: list[KnowledgeDocumentLifecycleAction] = []
    if should_show_cancel_action:
        actions.append(
            KnowledgeDocumentLifecycleAction(
                id="cancel",
                label="Остановить обработку",
                kind="destructive",
            )
        )
    if should_show_resume_action:
        actions.append(
            KnowledgeDocumentLifecycleAction(
                id="resume_processing",
                label="Продолжить обработку",
                kind="primary",
            )
        )
    if include_retry_later_action:
        actions.append(
            KnowledgeDocumentLifecycleAction(
                id="retry_later",
                label="Повторить позже",
                kind="secondary",
            )
        )
    if include_retry_failed_batches_action:
        actions.append(
            KnowledgeDocumentLifecycleAction(
                id="retry_failed_batches",
                label="Повторить проблемные части",
                kind="primary",
            )
        )
    if include_publish_ready_action:
        actions.append(
            KnowledgeDocumentLifecycleAction(
                id="publish_ready",
                label="Опубликовать готовые ответы",
                kind="primary",
                enabled=not is_processing,
            )
        )

    return KnowledgeDocumentLifecycleDecision(
        state=state,
        stop_reason=stop_reason,
        resume_policy=resume_policy,
        is_processing=is_processing,
        is_terminal=is_terminal,
        is_recoverable=is_recoverable,
        can_auto_resume=can_auto_resume,
        can_manual_resume=can_manual_resume,
        should_show_resume_action=should_show_resume_action,
        should_show_cancel_action=should_show_cancel_action,
        status_message=status_message,
        actions=tuple(actions),
    )


def _status_values(
    *,
    document_status: str,
    preprocessing_status: str | None,
    preprocessing_error: str | None,
    metrics: Mapping[str, object],
) -> tuple[str, ...]:
    values = [
        document_status,
        preprocessing_status,
        preprocessing_error,
        metrics.get("stage"),
    ]
    return tuple(_normalise(value) for value in values if _normalise(value))


def _normalise(value: object) -> str:
    return str(value or "").strip().lower()


def _has_status(values: tuple[str, ...], status: str) -> bool:
    return _normalise(status) in values


def _has_any_status(values: tuple[str, ...], statuses: frozenset[str]) -> bool:
    return bool(set(values).intersection(statuses))


def _has_legacy_user_cancelled_signal(values: tuple[str, ...]) -> bool:
    return bool(set(values).intersection(_LEGACY_USER_CANCELLED_EQUIVALENTS))


def _positive(value: int) -> bool:
    return value > 0


def _truthy_metric(metrics: Mapping[str, object], key: str) -> bool:
    value = metrics.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _has_explicit_safe_auto_recovery(metrics: Mapping[str, object]) -> bool:
    return _truthy_metric(metrics, "recoverable") and any(
        _truthy_metric(metrics, key) for key in _RECOVERABLE_AUTO_RESUME_KEYS
    )

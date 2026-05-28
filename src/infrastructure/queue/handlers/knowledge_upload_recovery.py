from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.llm.groq_router import (
    GroqFallbackExhaustedError,
    GroqRouteFailureType,
)

PROCESSING_PAUSED_QUOTA_STATUS = "processing_paused_quota"
NEEDS_RETRY_LATER_STATUS = "needs_retry_later"
NON_RETRYABLE_INPUT_TOO_LARGE_STATUS = "non_retryable_input_too_large"
DEFAULT_QUOTA_RETRY_AFTER_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class KnowledgeUploadRecoveryDecision:
    error_type: str
    document_status: str
    status_message: str
    recoverable: bool
    retry_after_seconds: int | None = None

    @property
    def can_retry_later(self) -> bool:
        return self.recoverable


def recoverable_llm_error_type(exc: BaseException) -> str | None:
    if isinstance(exc, GroqFallbackExhaustedError):
        return exc.failure_type.value

    message = str(exc).lower()
    if "groq_quota_exhausted" in message or "quota_exhausted" in message:
        return GroqRouteFailureType.QUOTA_EXHAUSTED.value
    if "input_too_large" in message or "request_too_large" in message:
        return GroqRouteFailureType.INPUT_TOO_LARGE.value
    if "all_fallbacks_exhausted" in message:
        return GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED.value
    return None


def recovery_decision_for_error_type(
    error_type: str,
) -> KnowledgeUploadRecoveryDecision:
    if error_type == GroqRouteFailureType.INPUT_TOO_LARGE.value:
        return KnowledgeUploadRecoveryDecision(
            error_type=error_type,
            document_status=NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
            status_message=(
                "Документ слишком большой для доступных LLM-маршрутов; "
                "нужна меньшая нарезка или меньший batch."
            ),
            recoverable=False,
        )
    if error_type == GroqRouteFailureType.QUOTA_EXHAUSTED.value:
        return KnowledgeUploadRecoveryDecision(
            error_type=error_type,
            document_status=PROCESSING_PAUSED_QUOTA_STATUS,
            status_message=(
                "Дневной лимит LLM исчерпан; уже сохранённый прогресс "
                "можно продолжить позже."
            ),
            recoverable=True,
            retry_after_seconds=DEFAULT_QUOTA_RETRY_AFTER_SECONDS,
        )
    return KnowledgeUploadRecoveryDecision(
        error_type=error_type,
        document_status=NEEDS_RETRY_LATER_STATUS,
        status_message=(
            "Все LLM fallback-маршруты исчерпаны; сохранённый прогресс "
            "можно повторить позже."
        ),
        recoverable=True,
    )


def recovery_metrics(decision: KnowledgeUploadRecoveryDecision) -> dict[str, object]:
    metrics: dict[str, object] = {
        "stage": decision.document_status,
        "status_message": decision.status_message,
        "error_type": decision.error_type,
        "recoverable": decision.recoverable,
        "partial_surfaces_available": True,
        "can_retry_later": decision.can_retry_later,
    }
    if decision.retry_after_seconds is not None:
        metrics["retry_after_seconds"] = decision.retry_after_seconds
    return metrics

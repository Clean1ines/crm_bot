from __future__ import annotations

from src.infrastructure.llm.groq_router import (
    GroqFallbackExhaustedError,
    GroqRouteFailureType,
)
from src.infrastructure.queue.handlers.knowledge_upload_recovery import (
    NEEDS_RETRY_LATER_STATUS,
    NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
    PROCESSING_PAUSED_QUOTA_STATUS,
    recoverable_llm_error_type,
    recovery_decision_for_error_type,
    recovery_metrics,
)


def test_recoverable_llm_error_type_reads_groq_fallback_error() -> None:
    exc = GroqFallbackExhaustedError(
        failure_type=GroqRouteFailureType.QUOTA_EXHAUSTED,
        message="quota exhausted",
    )

    assert recoverable_llm_error_type(exc) == "groq_quota_exhausted"


def test_recoverable_llm_error_type_reads_wrapped_validation_message() -> None:
    exc = ValueError("Groq fallback routing failed: groq_quota_exhausted")

    assert recoverable_llm_error_type(exc) == "groq_quota_exhausted"


def test_quota_exhaustion_pauses_processing_for_retry_later() -> None:
    decision = recovery_decision_for_error_type("groq_quota_exhausted")
    metrics = recovery_metrics(decision)

    assert decision.document_status == PROCESSING_PAUSED_QUOTA_STATUS
    assert decision.recoverable is True
    assert decision.can_retry_later is True
    assert metrics["partial_surfaces_available"] is True
    assert metrics["retry_after_seconds"] == 24 * 60 * 60


def test_input_too_large_is_non_retryable_document_input_failure() -> None:
    decision = recovery_decision_for_error_type("input_too_large")
    metrics = recovery_metrics(decision)

    assert decision.document_status == NON_RETRYABLE_INPUT_TOO_LARGE_STATUS
    assert decision.recoverable is False
    assert decision.can_retry_later is False
    assert metrics["can_retry_later"] is False


def test_all_fallbacks_exhausted_is_retry_later_not_bad_document() -> None:
    decision = recovery_decision_for_error_type("all_fallbacks_exhausted")
    metrics = recovery_metrics(decision)

    assert decision.document_status == NEEDS_RETRY_LATER_STATUS
    assert decision.recoverable is True
    assert metrics["partial_surfaces_available"] is True
    assert metrics["can_retry_later"] is True

from __future__ import annotations

from src.domain.project_plane.knowledge_document_lifecycle import (
    LEGACY_USER_CANCELLED_MESSAGE,
    NEEDS_RETRY_LATER_STATUS,
    NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
    PROCESSING_PAUSED_QUOTA_STATUS,
    resolve_knowledge_document_lifecycle,
)


def _action_ids(decision: object) -> set[str]:
    return {action.id for action in decision.actions}


def test_manual_cancel_legacy_fields_produce_manual_only_resume_action() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        preprocessing_metrics=None,
        chunk_count=3,
    )

    assert decision.state == "cancelled_by_user"
    assert decision.stop_reason == "user_cancelled"
    assert decision.resume_policy == "manual_only"
    assert decision.is_recoverable is True
    assert decision.can_manual_resume is True
    assert decision.can_auto_resume is False
    assert decision.should_show_resume_action is True
    assert "resume_processing" in _action_ids(decision)


def test_quota_pause_produces_auto_allowed_not_manual_only() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status=PROCESSING_PAUSED_QUOTA_STATUS,
        preprocessing_status=None,
        preprocessing_error=None,
        preprocessing_metrics=None,
    )

    assert decision.state == "paused_quota"
    assert decision.stop_reason == "quota_exhausted"
    assert decision.resume_policy == "auto_allowed"
    assert decision.is_recoverable is True
    assert decision.can_auto_resume is True
    assert decision.can_manual_resume is False
    assert decision.should_show_resume_action is False
    assert "resume_processing" not in _action_ids(decision)
    assert "retry_later" in _action_ids(decision)


def test_needs_retry_later_produces_auto_allowed() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error="all fallbacks exhausted",
        preprocessing_metrics={"stage": NEEDS_RETRY_LATER_STATUS},
    )

    assert decision.state == "paused_provider"
    assert decision.stop_reason == "provider_fallback_exhausted"
    assert decision.resume_policy == "auto_allowed"
    assert decision.can_auto_resume is True
    assert decision.can_manual_resume is False
    assert "retry_later" in _action_ids(decision)


def test_input_too_large_produces_forbidden_validation_failure() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status=NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
        preprocessing_error="input too large",
        preprocessing_metrics=None,
    )

    assert decision.state == "failed_validation"
    assert decision.stop_reason == "input_too_large"
    assert decision.resume_policy == "forbidden"
    assert decision.is_recoverable is False
    assert decision.can_auto_resume is False
    assert decision.can_manual_resume is False
    assert decision.actions == ()


def test_processing_produces_cancel_action() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="processing",
        preprocessing_status=None,
        preprocessing_error=None,
        preprocessing_metrics=None,
    )

    assert decision.state == "processing"
    assert decision.is_processing is True
    assert decision.should_show_cancel_action is True
    assert decision.resume_policy == "forbidden"
    assert "cancel" in _action_ids(decision)


def test_completed_processed_document_produces_not_needed() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="processed",
        preprocessing_status="completed",
        preprocessing_error=None,
        preprocessing_metrics=None,
        chunk_count=3,
    )

    assert decision.state == "completed"
    assert decision.stop_reason == "none"
    assert decision.resume_policy == "not_needed"
    assert decision.is_terminal is True
    assert decision.is_recoverable is False
    assert decision.can_auto_resume is False
    assert decision.can_manual_resume is False
    assert decision.actions == ()


def test_generic_failed_document_produces_failed_fatal_forbidden() -> None:
    decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error="unexpected backend error",
        preprocessing_metrics=None,
    )

    assert decision.state == "failed_fatal"
    assert decision.stop_reason == "fatal_error"
    assert decision.resume_policy == "forbidden"
    assert decision.is_recoverable is False
    assert decision.can_auto_resume is False
    assert decision.can_manual_resume is False
    assert decision.actions == ()


def test_recoverable_metrics_require_explicit_safe_key_for_generic_failed() -> None:
    unsafe_decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error="worker stopped",
        preprocessing_metrics={"recoverable": True},
    )
    safe_decision = resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error="worker stopped",
        preprocessing_metrics={"recoverable": True, "can_retry_later": True},
    )

    assert unsafe_decision.state == "failed_fatal"
    assert unsafe_decision.resume_policy == "forbidden"
    assert unsafe_decision.is_recoverable is False

    assert safe_decision.state == "interrupted"
    assert safe_decision.stop_reason == "worker_interrupted"
    assert safe_decision.resume_policy == "auto_allowed"
    assert safe_decision.is_recoverable is True
    assert safe_decision.can_auto_resume is True
    assert safe_decision.can_manual_resume is False
    assert "retry_later" in _action_ids(safe_decision)

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.domain.project_plane.knowledge_document_lifecycle import (
    LEGACY_USER_CANCELLED_MESSAGE,
    NEEDS_RETRY_LATER_STATUS,
    NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
    PROCESSING_PAUSED_QUOTA_STATUS,
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    resolve_knowledge_document_lifecycle,
)
from src.domain.project_plane.knowledge_faq_resume_policy import (
    decide_faq_surface_run_reuse,
)


@dataclass(frozen=True, slots=True)
class Run:
    id: str = "run-1"
    compiler_kind: str = "faq_retrieval_surface_compiler"
    prompt_version: str = "prompt-v1"
    status: str = "cancelled"
    error_type: str | None = "processing_cancelled"


def _decision_for_user_cancel():
    return resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        preprocessing_metrics=None,
        chunk_count=3,
    )


def _decision_for_quota_pause():
    return resolve_knowledge_document_lifecycle(
        document_status=PROCESSING_PAUSED_QUOTA_STATUS,
        preprocessing_status=PROCESSING_PAUSED_QUOTA_STATUS,
        preprocessing_error=None,
        preprocessing_metrics=None,
    )


def _decision_for_provider_pause():
    return resolve_knowledge_document_lifecycle(
        document_status=NEEDS_RETRY_LATER_STATUS,
        preprocessing_status=NEEDS_RETRY_LATER_STATUS,
        preprocessing_error=None,
        preprocessing_metrics={"stage": NEEDS_RETRY_LATER_STATUS},
    )


def _decision_for_input_too_large():
    return resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status=NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
        preprocessing_error="input too large",
        preprocessing_metrics=None,
    )


def _decision_for_fatal():
    return resolve_knowledge_document_lifecycle(
        document_status="error",
        preprocessing_status="failed",
        preprocessing_error="fatal boom",
        preprocessing_metrics=None,
    )


def test_normal_upload_never_reuses_user_cancelled_surface_run() -> None:
    decision = decide_faq_surface_run_reuse(
        latest_run=Run(),
        lifecycle_trigger=TRIGGER_NORMAL_UPLOAD,
        resume_run_id=None,
        lifecycle_decision=_decision_for_user_cancel(),
        expected_prompt_version="prompt-v1",
    )

    assert decision.reuse is False
    assert decision.reason == "normal_upload_never_reuses_surface_run"


def test_explicit_resume_reuses_matching_user_cancelled_run() -> None:
    decision = decide_faq_surface_run_reuse(
        latest_run=Run(id="run-1"),
        lifecycle_trigger=TRIGGER_EXPLICIT_USER_RESUME,
        resume_run_id="run-1",
        lifecycle_decision=_decision_for_user_cancel(),
        expected_prompt_version="prompt-v1",
    )

    assert decision.reuse is True


@pytest.mark.parametrize(
    "lifecycle_decision",
    [
        _decision_for_quota_pause(),
        _decision_for_provider_pause(),
        _decision_for_input_too_large(),
        _decision_for_fatal(),
    ],
)
def test_explicit_resume_rejected_without_manual_lifecycle_permission(
    lifecycle_decision: object,
) -> None:
    decision = decide_faq_surface_run_reuse(
        latest_run=Run(id="run-1"),
        lifecycle_trigger=TRIGGER_EXPLICIT_USER_RESUME,
        resume_run_id="run-1",
        lifecycle_decision=lifecycle_decision,
        expected_prompt_version="prompt-v1",
    )

    assert decision.reuse is False


def test_quota_recovery_reuses_failed_non_cancelled_run_when_auto_allowed() -> None:
    decision = decide_faq_surface_run_reuse(
        latest_run=Run(
            id="run-1",
            status="failed",
            error_type="GroqFallbackExhaustedError",
        ),
        lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
        resume_run_id="run-1",
        lifecycle_decision=_decision_for_quota_pause(),
        expected_prompt_version="prompt-v1",
    )

    assert decision.reuse is True


def test_quota_recovery_does_not_reuse_user_cancelled_run() -> None:
    decision = decide_faq_surface_run_reuse(
        latest_run=Run(id="run-1", status="cancelled"),
        lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
        resume_run_id="run-1",
        lifecycle_decision=_decision_for_quota_pause(),
        expected_prompt_version="prompt-v1",
    )

    assert decision.reuse is False
    assert decision.reason == "auto_recovery_must_not_reuse_user_cancelled_run"


def test_input_too_large_never_reuses_surface_run() -> None:
    decision = decide_faq_surface_run_reuse(
        latest_run=Run(id="run-1", status="failed", error_type="input_too_large"),
        lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
        resume_run_id="run-1",
        lifecycle_decision=_decision_for_input_too_large(),
        expected_prompt_version="prompt-v1",
    )

    assert decision.reuse is False
    assert decision.reason == "document_lifecycle_stop_reason_forbids_resume"

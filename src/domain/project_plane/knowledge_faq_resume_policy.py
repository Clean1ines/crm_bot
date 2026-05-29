from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_document_lifecycle import (
    RESUME_POLICY_FORBIDDEN,
    STOP_REASON_FATAL_ERROR,
    STOP_REASON_INPUT_TOO_LARGE,
    STOP_REASON_VALIDATION_FAILED,
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    TRIGGER_STALE_JOB_RECOVERY,
    TRIGGER_WORKER_RECOVERY,
    KnowledgeDocumentLifecycleDecision,
    KnowledgeDocumentLifecycleTrigger,
)

FAQ_SURFACE_COMPILER_KIND = "faq_retrieval_surface_compiler"
FAQ_PROCESSING_CANCELLED_ERROR_TYPE = "processing_cancelled"

FAQ_REUSABLE_RUN_STATUSES = frozenset({"running", "failed", "cancelled"})
FAQ_AUTO_RESUME_RUN_STATUSES = frozenset({"running", "failed"})
FAQ_AUTO_RECOVERY_TRIGGERS = frozenset(
    {
        TRIGGER_WORKER_RECOVERY,
        TRIGGER_QUOTA_RECOVERY,
        TRIGGER_STALE_JOB_RECOVERY,
    }
)
FAQ_FORBIDDEN_STOP_REASONS = frozenset(
    {
        STOP_REASON_INPUT_TOO_LARGE,
        STOP_REASON_VALIDATION_FAILED,
        STOP_REASON_FATAL_ERROR,
    }
)


class KnowledgeFaqSurfaceRunLike(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def compiler_kind(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def error_type(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class KnowledgeFaqSurfaceRunReuseDecision:
    reuse: bool
    reason: str


def decide_faq_surface_run_reuse(
    *,
    latest_run: KnowledgeFaqSurfaceRunLike | None,
    lifecycle_trigger: KnowledgeDocumentLifecycleTrigger,
    resume_run_id: str | None,
    lifecycle_decision: KnowledgeDocumentLifecycleDecision,
    expected_prompt_version: str,
    manual_resume_authorized_by_lifecycle: bool = False,
) -> KnowledgeFaqSurfaceRunReuseDecision:
    """Pure FAQ surface compiler run reuse policy.

    This function deliberately knows nothing about application services,
    repositories, queues, SQL, LLM adapters, or HTTP details.
    """

    if lifecycle_trigger == TRIGGER_NORMAL_UPLOAD:
        return _reject("normal_upload_never_reuses_surface_run")

    if latest_run is None:
        return _reject("surface_run_missing")

    if latest_run.compiler_kind != FAQ_SURFACE_COMPILER_KIND:
        return _reject("surface_run_wrong_compiler_kind")

    if latest_run.prompt_version != expected_prompt_version:
        return _reject("surface_run_prompt_version_mismatch")

    if latest_run.status not in FAQ_REUSABLE_RUN_STATUSES:
        return _reject("surface_run_status_not_reusable")

    if lifecycle_decision.stop_reason in FAQ_FORBIDDEN_STOP_REASONS:
        return _reject("document_lifecycle_stop_reason_forbids_resume")

    if lifecycle_decision.resume_policy == RESUME_POLICY_FORBIDDEN and not (
        lifecycle_trigger == TRIGGER_EXPLICIT_USER_RESUME
        and manual_resume_authorized_by_lifecycle
    ):
        return _reject("document_lifecycle_resume_policy_forbids_resume")

    if lifecycle_trigger == TRIGGER_EXPLICIT_USER_RESUME:
        if not resume_run_id:
            return _reject("explicit_resume_requires_resume_run_id")
        if resume_run_id != latest_run.id:
            return _reject("explicit_resume_run_id_mismatch")
        if not (
            lifecycle_decision.can_manual_resume
            or manual_resume_authorized_by_lifecycle
        ):
            return _reject("explicit_resume_requires_manual_lifecycle_permission")
        if not _is_user_cancelled_run(latest_run):
            return _reject("explicit_resume_requires_user_cancelled_run")
        return _allow("explicit_user_resume_reuses_user_cancelled_run")

    if lifecycle_trigger in FAQ_AUTO_RECOVERY_TRIGGERS:
        if resume_run_id is not None and resume_run_id != latest_run.id:
            return _reject("auto_recovery_resume_run_id_mismatch")
        if not lifecycle_decision.can_auto_resume:
            return _reject("auto_recovery_requires_auto_lifecycle_permission")
        if _is_user_cancelled_run(latest_run):
            return _reject("auto_recovery_must_not_reuse_user_cancelled_run")
        if latest_run.status not in FAQ_AUTO_RESUME_RUN_STATUSES:
            return _reject("auto_recovery_requires_running_or_failed_run")
        return _allow("auto_recovery_reuses_interrupted_run")

    return _reject("unsupported_lifecycle_trigger")


def should_reuse_faq_surface_run(
    *,
    latest_run: KnowledgeFaqSurfaceRunLike | None,
    lifecycle_trigger: KnowledgeDocumentLifecycleTrigger,
    resume_run_id: str | None,
    lifecycle_decision: KnowledgeDocumentLifecycleDecision,
    expected_prompt_version: str,
    manual_resume_authorized_by_lifecycle: bool = False,
) -> bool:
    return decide_faq_surface_run_reuse(
        latest_run=latest_run,
        lifecycle_trigger=lifecycle_trigger,
        resume_run_id=resume_run_id,
        lifecycle_decision=lifecycle_decision,
        expected_prompt_version=expected_prompt_version,
        manual_resume_authorized_by_lifecycle=manual_resume_authorized_by_lifecycle,
    ).reuse


def _is_user_cancelled_run(run: KnowledgeFaqSurfaceRunLike) -> bool:
    return (
        run.status == "cancelled"
        or run.error_type == FAQ_PROCESSING_CANCELLED_ERROR_TYPE
    )


def _allow(reason: str) -> KnowledgeFaqSurfaceRunReuseDecision:
    return KnowledgeFaqSurfaceRunReuseDecision(reuse=True, reason=reason)


def _reject(reason: str) -> KnowledgeFaqSurfaceRunReuseDecision:
    return KnowledgeFaqSurfaceRunReuseDecision(reuse=False, reason=reason)

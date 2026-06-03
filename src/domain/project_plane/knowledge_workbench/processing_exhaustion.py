from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    KnowledgeProcessingRun,
    ProcessingRunStatus,
    ResumePolicy,
)


@dataclass(frozen=True, slots=True)
class ProcessingExhaustionTransition:
    document_status_after: KnowledgeDocumentStatus
    processing_run_status_after: ProcessingRunStatus
    resume_policy_after: ResumePolicy
    automatic_recovery_allowed_after: bool
    error_kind: str
    error_message_user: str
    error_message_internal: str
    reason: str


def decide_processing_exhaustion_transition(
    *,
    document: KnowledgeDocument,
    processing_run: KnowledgeProcessingRun,
    error_message: str,
) -> ProcessingExhaustionTransition:
    """Map exhausted queue retries to a Workbench lifecycle state.

    Exhausted queue retries are not the same as user cancellation and must not
    revive the retired process_knowledge_upload recovery path. Workbench stores
    the failure directly on its document/run lifecycle so manual resume and
    automatic recovery policies can reason from first-class Workbench state.
    """

    normalized_error = error_message.strip() or "workbench processing retries exhausted"
    lowered = normalized_error.lower()

    if document.status is KnowledgeDocumentStatus.DELETED:
        return ProcessingExhaustionTransition(
            document_status_after=KnowledgeDocumentStatus.DELETED,
            processing_run_status_after=ProcessingRunStatus.DELETED,
            resume_policy_after=ResumePolicy.FORBIDDEN,
            automatic_recovery_allowed_after=False,
            error_kind="deleted_document",
            error_message_user="Документ уже удалён.",
            error_message_internal=normalized_error,
            reason="deleted document cannot be recovered",
        )

    if processing_run.status is ProcessingRunStatus.CANCELLED_BY_USER:
        return ProcessingExhaustionTransition(
            document_status_after=KnowledgeDocumentStatus.CANCELLED,
            processing_run_status_after=ProcessingRunStatus.CANCELLED_BY_USER,
            resume_policy_after=ResumePolicy.MANUAL_ONLY,
            automatic_recovery_allowed_after=False,
            error_kind="cancelled_by_user",
            error_message_user="Обработка была отменена пользователем.",
            error_message_internal=normalized_error,
            reason="user cancelled processing keeps manual resume policy",
        )

    if "quota" in lowered or "rate limit" in lowered or "429" in lowered:
        return ProcessingExhaustionTransition(
            document_status_after=KnowledgeDocumentStatus.PAUSED,
            processing_run_status_after=ProcessingRunStatus.PAUSED_QUOTA,
            resume_policy_after=ResumePolicy.AUTO_ALLOWED,
            automatic_recovery_allowed_after=True,
            error_kind="quota_exhausted",
            error_message_user=(
                "Обработка временно приостановлена: исчерпан лимит LLM-провайдера."
            ),
            error_message_internal=normalized_error,
            reason="quota exhaustion can be retried automatically later",
        )

    if (
        "fallback" in lowered
        or "provider" in lowered
        or "groq" in lowered
        or "llm" in lowered
    ):
        return ProcessingExhaustionTransition(
            document_status_after=KnowledgeDocumentStatus.PAUSED,
            processing_run_status_after=ProcessingRunStatus.PAUSED_PROVIDER,
            resume_policy_after=ResumePolicy.AUTO_ALLOWED,
            automatic_recovery_allowed_after=True,
            error_kind="provider_exhausted",
            error_message_user=(
                "Обработка временно приостановлена: LLM-провайдер недоступен."
            ),
            error_message_internal=normalized_error,
            reason="provider exhaustion can be retried automatically later",
        )

    return ProcessingExhaustionTransition(
        document_status_after=KnowledgeDocumentStatus.PAUSED,
        processing_run_status_after=ProcessingRunStatus.PAUSED_SERVER_INTERRUPTED,
        resume_policy_after=ResumePolicy.AUTO_ALLOWED,
        automatic_recovery_allowed_after=True,
        error_kind="worker_retry_exhausted",
        error_message_user=(
            "Обработка временно приостановлена после нескольких неудачных попыток."
        ),
        error_message_internal=normalized_error,
        reason="worker retry exhaustion is recoverable by Workbench lifecycle",
    )


__all__ = [
    "ProcessingExhaustionTransition",
    "decide_processing_exhaustion_transition",
]

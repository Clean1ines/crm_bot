from __future__ import annotations

from collections.abc import Mapping

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowEventType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


PROJECTION_VERSION = 1

_PROJECTION_TYPES = {
    WorkbenchRagEvalWorkflowEventType.RUN_STARTED.value: "rag_eval_run_started",
    WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_WORK_ITEM_SCHEDULED.value: (
        "rag_eval_question_generation_work_item_scheduled"
    ),
    WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_DISPATCH_ATTEMPT_PREPARED.value: (
        "rag_eval_question_generation_dispatch_attempt_prepared"
    ),
    WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_ATTEMPT_COMPLETED.value: (
        "rag_eval_question_generation_attempt_completed"
    ),
    WorkbenchRagEvalWorkflowEventType.QUESTION_GENERATION_PROGRESS_RECONCILED.value: (
        "rag_eval_question_generation_progress_reconciled"
    ),
    WorkbenchRagEvalWorkflowEventType.RETRIEVAL_EVALUATION_COMPLETED.value: (
        "rag_eval_retrieval_evaluation_completed"
    ),
    WorkbenchRagEvalWorkflowEventType.ADJUDICATION_WORK_ITEM_SCHEDULED.value: (
        "rag_eval_adjudication_work_item_scheduled"
    ),
    WorkbenchRagEvalWorkflowEventType.ADJUDICATION_DISPATCH_ATTEMPT_PREPARED.value: (
        "rag_eval_adjudication_dispatch_attempt_prepared"
    ),
    WorkbenchRagEvalWorkflowEventType.ADJUDICATION_ATTEMPT_COMPLETED.value: (
        "rag_eval_adjudication_attempt_completed"
    ),
    WorkbenchRagEvalWorkflowEventType.ADJUDICATION_PROGRESS_RECONCILED.value: (
        "rag_eval_adjudication_progress_reconciled"
    ),
    WorkbenchRagEvalWorkflowEventType.PROMOTION_CANDIDATES_READY.value: (
        "rag_eval_promotion_candidates_ready"
    ),
    WorkbenchRagEvalWorkflowEventType.PROMOTIONS_APPLIED.value: (
        "rag_eval_promotions_applied"
    ),
    WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_CREATED.value: (
        "rag_eval_embedding_revision_created"
    ),
    WorkbenchRagEvalWorkflowEventType.VERIFICATION_BATCH_COMPLETED.value: (
        "rag_eval_verification_batch_completed"
    ),
    WorkbenchRagEvalWorkflowEventType.VERIFICATION_COMPLETED.value: (
        "rag_eval_verification_completed"
    ),
    WorkbenchRagEvalWorkflowEventType.VERIFICATION_REGRESSION_FAILED.value: (
        "rag_eval_verification_regression_failed"
    ),
    WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_ACCEPTED.value: (
        "rag_eval_embedding_revision_accepted"
    ),
    WorkbenchRagEvalWorkflowEventType.EMBEDDING_REVISION_ROLLED_BACK.value: (
        "rag_eval_embedding_revision_rolled_back"
    ),
    WorkbenchRagEvalWorkflowEventType.RUN_COMPLETED.value: "rag_eval_run_completed",
    WorkbenchRagEvalWorkflowEventType.RUN_BLOCKED.value: "rag_eval_run_blocked",
    WorkbenchRagEvalWorkflowEventType.RUN_FAILED.value: "rag_eval_run_failed",
}

_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "rag_eval_run_id",
        "run_id",
        "project_id",
        "source_document_ref",
        "phase",
        "status",
        "revision_id",
        "runtime_entry_id",
        "promotion_ids",
        "verification_id",
        "processed_count",
        "remaining_count",
        "succeeded_count",
        "failed_count",
        "query_count",
        "outcome_count",
        "decision",
        "failure_reasons",
        "metrics",
        "work_item_id",
        "dispatch_attempt_id",
        "attempt_number",
        "attempt_state",
        "model_ref",
        "account_ref",
        "capacity_wait_seconds",
        "classification_counts",
        "candidate_count",
        "applied_count",
        "approved_count",
        "rejected_count",
        "error_message",
    }
)

_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "embedding",
        "vector",
        "previous_embedding",
        "new_embedding",
        "provider_api_key",
        "api_key",
        "secret",
    }
)


class WorkbenchRagEvalFrontendWorkflowEventProjector:
    """Projects allowlisted Workbench RAG Eval workflow events for frontend SSE."""

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        if not isinstance(event, WorkflowEvent):
            raise TypeError("event must be WorkflowEvent")
        projection_type = _PROJECTION_TYPES.get(event.event_type)
        if projection_type is None:
            return None
        if event.sequence_number is None:
            raise ValueError(
                "event sequence_number is required for frontend projection"
            )

        project_id = _payload_text(event.payload, "project_id")
        document_id = _document_id(
            payload=event.payload,
            project_id=project_id,
            workflow_run_id=event.workflow_run_id,
        )
        return FrontendWorkflowEvent(
            projection_event_id=(
                f"frontend-workflow-event:{event.event_id.value}:"
                f"{projection_type}:v{PROJECTION_VERSION}"
            ),
            source_event_id=event.event_id.value,
            source_sequence_number=event.sequence_number,
            projection_version=PROJECTION_VERSION,
            projection_type=projection_type,
            event_type=event.event_type,
            operation_key=_optional_payload_text(event.payload, "operation_key"),
            canonical_phase=_payload_text(event.payload, "phase", fallback="RAG_EVAL"),
            workflow_run_id=event.workflow_run_id,
            project_id=project_id,
            document_id=document_id,
            payload=_allowed_payload(event.payload),
            occurred_at=event.occurred_at,
            projected_at=event.occurred_at,
            causation_command_id=event.causation_command_id.value
            if event.causation_command_id is not None
            else None,
            correlation_id=event.correlation_id,
        )


def _document_id(
    *,
    payload: Mapping[str, object],
    project_id: str,
    workflow_run_id: str,
) -> str:
    source_document_ref = _optional_payload_text(payload, "source_document_ref")
    if source_document_ref is not None:
        return source_document_ref
    return f"rag-eval:{project_id}:{workflow_run_id}"


def _allowed_payload(payload: Mapping[str, object]) -> dict[str, object]:
    patch: dict[str, object] = {}
    for key in _ALLOWED_PAYLOAD_KEYS:
        if key in _FORBIDDEN_PAYLOAD_KEYS or key not in payload:
            continue
        value = payload[key]
        if value is not None:
            patch[key] = value
    return patch


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if fallback is not None and fallback.strip():
        return fallback.strip()
    raise ValueError(f"event payload {key} must be non-empty text")


def _optional_payload_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None

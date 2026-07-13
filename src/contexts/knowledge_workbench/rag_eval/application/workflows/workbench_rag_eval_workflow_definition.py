from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkbenchRagEvalWorkflowPhase(StrEnum):
    SCOPE_RESOLUTION = "SCOPE_RESOLUTION"
    QUESTION_GENERATION_SCHEDULING = "QUESTION_GENERATION_SCHEDULING"
    QUESTION_GENERATION = "QUESTION_GENERATION"
    RETRIEVAL_EVALUATION = "RETRIEVAL_EVALUATION"
    ADJUDICATION_SCHEDULING = "ADJUDICATION_SCHEDULING"
    ADJUDICATION = "ADJUDICATION"
    PROMOTION_REVIEW = "PROMOTION_REVIEW"
    PROMOTION_APPLICATION = "PROMOTION_APPLICATION"
    POST_PROMOTION_VERIFICATION = "POST_PROMOTION_VERIFICATION"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class WorkbenchRagEvalWorkflowCommandType(StrEnum):
    SCHEDULE_QUESTION_GENERATION_WORK = "ScheduleRagEvalQuestionGenerationWork"
    PREPARE_QUESTION_GENERATION_DISPATCH_BATCH = (
        "PrepareRagEvalQuestionGenerationDispatchBatch"
    )
    EXECUTE_QUESTION_GENERATION = "ExecuteRagEvalQuestionGeneration"
    RECONCILE_QUESTION_GENERATION_PROGRESS = (
        "ReconcileRagEvalQuestionGenerationProgress"
    )
    RUN_RETRIEVAL_EVALUATION = "RunRagEvalRetrievalEvaluation"
    SCHEDULE_ADJUDICATION_WORK = "ScheduleRagEvalAdjudicationWork"
    PREPARE_ADJUDICATION_DISPATCH_BATCH = "PrepareRagEvalAdjudicationDispatchBatch"
    EXECUTE_ADJUDICATION = "ExecuteRagEvalAdjudication"
    RECONCILE_ADJUDICATION_PROGRESS = "ReconcileRagEvalAdjudicationProgress"
    APPLY_PROMOTIONS = "ApplyRagEvalPromotions"
    RUN_POST_PROMOTION_VERIFICATION = "RunRagEvalPostPromotionVerification"
    ACCEPT_EMBEDDING_REVISION = "AcceptRagEvalEmbeddingRevision"
    ROLLBACK_EMBEDDING_REVISION = "RollbackRagEvalEmbeddingRevision"


class WorkbenchRagEvalWorkflowEventType(StrEnum):
    RUN_STARTED = "RagEvalRunStarted"
    SCOPE_RESOLVED = "RagEvalScopeResolved"

    QUESTION_GENERATION_WORK_SCHEDULED = "RagEvalQuestionGenerationWorkScheduled"
    QUESTION_GENERATION_WORK_ITEM_SCHEDULED = (
        "RagEvalQuestionGenerationWorkItemScheduled"
    )
    QUESTION_GENERATION_DISPATCH_BATCH_PREPARED = (
        "RagEvalQuestionGenerationDispatchBatchPrepared"
    )
    QUESTION_GENERATION_DISPATCH_ATTEMPT_PREPARED = (
        "RagEvalQuestionGenerationDispatchAttemptPrepared"
    )
    QUESTION_GENERATION_ATTEMPT_COMPLETED = "RagEvalQuestionGenerationAttemptCompleted"
    QUESTION_GENERATION_CAPACITY_OBSERVED = "RagEvalQuestionGenerationCapacityObserved"
    QUESTION_GENERATION_PROGRESS_RECONCILED = (
        "RagEvalQuestionGenerationProgressReconciled"
    )
    QUESTION_GENERATION_COMPLETED = "RagEvalQuestionGenerationCompleted"

    RETRIEVAL_EVALUATION_COMPLETED = "RagEvalRetrievalEvaluationCompleted"

    ADJUDICATION_WORK_SCHEDULED = "RagEvalAdjudicationWorkScheduled"
    ADJUDICATION_WORK_ITEM_SCHEDULED = "RagEvalAdjudicationWorkItemScheduled"
    ADJUDICATION_DISPATCH_BATCH_PREPARED = "RagEvalAdjudicationDispatchBatchPrepared"
    ADJUDICATION_DISPATCH_ATTEMPT_PREPARED = (
        "RagEvalAdjudicationDispatchAttemptPrepared"
    )
    ADJUDICATION_ATTEMPT_COMPLETED = "RagEvalAdjudicationAttemptCompleted"
    ADJUDICATION_CAPACITY_OBSERVED = "RagEvalAdjudicationCapacityObserved"
    ADJUDICATION_PROGRESS_RECONCILED = "RagEvalAdjudicationProgressReconciled"
    ADJUDICATION_COMPLETED = "RagEvalAdjudicationCompleted"

    PROMOTION_CANDIDATES_READY = "RagEvalPromotionCandidatesReady"
    PROMOTIONS_APPLIED = "RAG_EVAL_PROMOTIONS_APPLIED"
    EMBEDDING_REVISION_CREATED = "RAG_EVAL_EMBEDDING_REVISION_CREATED"
    VERIFICATION_COMPLETED = "RagEvalVerificationCompleted"
    EMBEDDING_REVISION_ACCEPTED = "RagEvalEmbeddingRevisionAccepted"
    EMBEDDING_REVISION_ROLLED_BACK = "RagEvalEmbeddingRevisionRolledBack"

    RUN_COMPLETED = "RagEvalRunCompleted"
    RUN_BLOCKED = "RagEvalRunBlocked"
    RUN_FAILED = "RagEvalRunFailed"


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalWorkflowOperation:
    operation_key: str
    phase: WorkbenchRagEvalWorkflowPhase
    command_type: WorkbenchRagEvalWorkflowCommandType
    next_command_types: tuple[
        WorkbenchRagEvalWorkflowCommandType,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operation_key, str):
            raise TypeError("operation_key must be str")
        if not self.operation_key.strip():
            raise ValueError("operation_key must be non-empty")
        if not isinstance(self.phase, WorkbenchRagEvalWorkflowPhase):
            raise TypeError("phase must be WorkbenchRagEvalWorkflowPhase")
        if not isinstance(
            self.command_type,
            WorkbenchRagEvalWorkflowCommandType,
        ):
            raise TypeError("command_type must be WorkbenchRagEvalWorkflowCommandType")
        for next_command_type in self.next_command_types:
            if not isinstance(
                next_command_type,
                WorkbenchRagEvalWorkflowCommandType,
            ):
                raise TypeError(
                    "next_command_types must contain "
                    "WorkbenchRagEvalWorkflowCommandType"
                )


WORKBENCH_RAG_EVAL_WORKFLOW_OPERATIONS = (
    WorkbenchRagEvalWorkflowOperation(
        operation_key="schedule_question_generation_work",
        phase=(WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION_SCHEDULING),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.SCHEDULE_QUESTION_GENERATION_WORK
        ),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="prepare_question_generation_dispatch_batch",
        phase=WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION,
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH
        ),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="execute_question_generation",
        phase=WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION,
        command_type=(WorkbenchRagEvalWorkflowCommandType.EXECUTE_QUESTION_GENERATION),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="reconcile_question_generation_progress",
        phase=WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION,
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS
        ),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH,
            WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="run_retrieval_evaluation",
        phase=WorkbenchRagEvalWorkflowPhase.RETRIEVAL_EVALUATION,
        command_type=(WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="schedule_adjudication_work",
        phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION_SCHEDULING,
        command_type=(WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="prepare_adjudication_dispatch_batch",
        phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION,
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_ADJUDICATION_DISPATCH_BATCH
        ),
        next_command_types=(WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION,),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="execute_adjudication",
        phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION,
        command_type=(WorkbenchRagEvalWorkflowCommandType.EXECUTE_ADJUDICATION),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="reconcile_adjudication_progress",
        phase=WorkbenchRagEvalWorkflowPhase.ADJUDICATION,
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.RECONCILE_ADJUDICATION_PROGRESS
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="apply_promotions",
        phase=WorkbenchRagEvalWorkflowPhase.PROMOTION_APPLICATION,
        command_type=(WorkbenchRagEvalWorkflowCommandType.APPLY_PROMOTIONS),
        next_command_types=(
            WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION,
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="run_post_promotion_verification",
        phase=(WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.RUN_POST_PROMOTION_VERIFICATION
        ),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="accept_embedding_revision",
        phase=WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION,
        command_type=(WorkbenchRagEvalWorkflowCommandType.ACCEPT_EMBEDDING_REVISION),
    ),
    WorkbenchRagEvalWorkflowOperation(
        operation_key="rollback_embedding_revision",
        phase=WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION,
        command_type=(WorkbenchRagEvalWorkflowCommandType.ROLLBACK_EMBEDDING_REVISION),
    ),
)


def operation_for_command_type(
    command_type: WorkbenchRagEvalWorkflowCommandType,
) -> WorkbenchRagEvalWorkflowOperation:
    if not isinstance(command_type, WorkbenchRagEvalWorkflowCommandType):
        raise TypeError("command_type must be WorkbenchRagEvalWorkflowCommandType")
    for operation in WORKBENCH_RAG_EVAL_WORKFLOW_OPERATIONS:
        if operation.command_type is command_type:
            return operation
    raise KeyError(command_type)


def command_type_from_value(
    value: str,
) -> WorkbenchRagEvalWorkflowCommandType:
    if not isinstance(value, str):
        raise TypeError("value must be str")
    try:
        return WorkbenchRagEvalWorkflowCommandType(value)
    except ValueError as exc:
        raise ValueError(f"unknown Workbench RAG Eval command type: {value}") from exc

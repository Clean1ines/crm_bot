from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WORKBENCH_RAG_EVAL_WORKFLOW_OPERATIONS,
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowEventType,
    WorkbenchRagEvalWorkflowPhase,
    command_type_from_value,
    operation_for_command_type,
)


def test_rag_eval_workflow_family_has_required_phases() -> None:
    assert set(WorkbenchRagEvalWorkflowPhase) == {
        WorkbenchRagEvalWorkflowPhase.SCOPE_RESOLUTION,
        WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION_SCHEDULING,
        WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION,
        WorkbenchRagEvalWorkflowPhase.RETRIEVAL_EVALUATION,
        WorkbenchRagEvalWorkflowPhase.ADJUDICATION_SCHEDULING,
        WorkbenchRagEvalWorkflowPhase.ADJUDICATION,
        WorkbenchRagEvalWorkflowPhase.PROMOTION_REVIEW,
        WorkbenchRagEvalWorkflowPhase.PROMOTION_APPLICATION,
        WorkbenchRagEvalWorkflowPhase.POST_PROMOTION_VERIFICATION,
        WorkbenchRagEvalWorkflowPhase.COMPLETED,
        WorkbenchRagEvalWorkflowPhase.BLOCKED,
        WorkbenchRagEvalWorkflowPhase.FAILED,
    }


def test_rag_eval_command_values_do_not_collide_with_extraction_names() -> None:
    values = tuple(
        command_type.value for command_type in WorkbenchRagEvalWorkflowCommandType
    )

    assert len(values) == len(set(values))
    assert "PrepareClaimBuilderDispatchBatch" not in values
    assert "ExecuteClaimBuilderSection" not in values
    assert "ReconcileClaimBuilderProgress" not in values


def test_every_defined_operation_has_unique_command_type() -> None:
    command_types = tuple(
        operation.command_type for operation in WORKBENCH_RAG_EVAL_WORKFLOW_OPERATIONS
    )

    assert len(command_types) == len(set(command_types))


def test_operation_lookup_is_fail_fast() -> None:
    operation = operation_for_command_type(
        WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH
    )

    assert operation.operation_key == ("prepare_question_generation_dispatch_batch")
    assert operation.phase is (WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION)


def test_command_type_from_value_rejects_unknown_command() -> None:
    with pytest.raises(
        ValueError,
        match="unknown Workbench RAG Eval command type",
    ):
        command_type_from_value("PrepareClaimBuilderDispatchBatch")


def test_required_terminal_events_exist() -> None:
    assert WorkbenchRagEvalWorkflowEventType.RUN_COMPLETED.value == (
        "RagEvalRunCompleted"
    )
    assert WorkbenchRagEvalWorkflowEventType.RUN_BLOCKED.value == ("RagEvalRunBlocked")
    assert WorkbenchRagEvalWorkflowEventType.RUN_FAILED.value == ("RagEvalRunFailed")

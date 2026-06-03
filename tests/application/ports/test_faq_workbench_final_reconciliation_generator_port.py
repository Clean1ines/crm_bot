from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.ports.faq_workbench_final_reconciliation_generator import (
    FaqWorkbenchFinalReconciliationGenerationCommand,
    FaqWorkbenchFinalReconciliationGenerationError,
    FaqWorkbenchFinalReconciliationGenerationResult,
    FinalReconciliationAdvice,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    RegistrySnapshot,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmTokenUsage,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
)


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id="snapshot-1",
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="registry-update-application-node",
        sequence_number=2,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=0,
        relation_count=0,
        claim_observation_count=0,
        update_count=0,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _success_invocation() -> LlmJsonInvocationResult:
    return LlmJsonInvocationResult(
        status=LlmInvocationStatus.SUCCESS,
        parsed_json={"surface_adjustments": [], "relations": [], "merge_decisions": []},
        raw_text='{"surface_adjustments":[],"relations":[],"merge_decisions":[]}',
        token_usage=LlmTokenUsage(prompt_tokens=11, completion_tokens=7),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-final",
                attempt_index=0,
                status=LlmRouteAttemptStatus.SUCCESS,
            ),
        ),
    )


def test_final_reconciliation_command_requires_node_run_id() -> None:
    with pytest.raises(DomainInvariantError, match="node_run_id"):
        FaqWorkbenchFinalReconciliationGenerationCommand(
            node_run_id="",
            registry_snapshot=_snapshot(),
            canonical_facts=(),
            proposed_final_surfaces=(),
            proposed_relations=(),
            proposed_merge_decisions=(),
            aggregate_metrics={},
        )


def test_final_reconciliation_command_requires_object_metrics() -> None:
    with pytest.raises(DomainInvariantError, match="aggregate_metrics"):
        FaqWorkbenchFinalReconciliationGenerationCommand(
            node_run_id="node-run-1",
            registry_snapshot=_snapshot(),
            canonical_facts=(),
            proposed_final_surfaces=(),
            proposed_relations=(),
            proposed_merge_decisions=(),
            aggregate_metrics=[],
        )


def test_final_reconciliation_advice_counts_all_advisory_suggestions() -> None:
    advice = FinalReconciliationAdvice(
        surface_adjustments=({"surface_key": "surface-1", "action": "tighten"},),
        relations=({"source": "surface-1", "target": "surface-2"},),
        merge_decisions=({"source": "surface-1", "target": "surface-3"},),
        warnings=("review suggested",),
        metrics={"bounded_final_reconciliation": True},
    )
    result = FaqWorkbenchFinalReconciliationGenerationResult(
        advice=advice,
        invocation=_success_invocation(),
        raw_output_artifact_payload={"raw_text": "{}"},
        parsed_output_artifact_payload={"surface_adjustments": []},
    )

    assert result.surface_adjustment_count == 1
    assert result.relation_count == 1
    assert result.merge_decision_count == 1
    assert result.suggestion_count == 3


def test_final_reconciliation_error_carries_failed_invocation_result() -> None:
    failed = LlmJsonInvocationResult(
        status=LlmInvocationStatus.PROVIDER_ERROR,
        parsed_json=None,
        raw_text="provider failed",
        token_usage=LlmTokenUsage(prompt_tokens=5, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-final",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="provider_error",
            ),
        ),
        failure=LlmInvocationFailure(
            status=LlmInvocationStatus.PROVIDER_ERROR,
            error_kind="provider_error",
            user_message="ИИ временно недоступен.",
            internal_message="provider failed during final reconciliation",
        ),
    )

    error = FaqWorkbenchFinalReconciliationGenerationError(failed)

    assert error.result is failed
    assert "final reconciliation generation failed" in str(error)

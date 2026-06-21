from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.llm_provider_capacity_observed_frontend_workflow_event_projector import (
    LlmProviderCapacityObservedFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _base_payload(
    *,
    operation_key: str = "execute_claim_builder_section",
    canonical_phase: str = (
        KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    ),
) -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "dispatch_attempt_id": "work-1:attempt:1",
        "work_item_id": "work-1",
        "operation_key": operation_key,
        "canonical_phase": canonical_phase,
        "provider": "groq",
        "account_ref": "groq_org_primary",
        "model_ref": "qwen/qwen3-32b",
        "remaining_minute_requests": 2,
        "remaining_minute_tokens": 7000,
        "remaining_daily_requests": 100,
        "remaining_daily_tokens": 50000,
        "minute_reset_at": "2026-06-21T12:01:00+00:00",
        "actual_prompt_tokens": 10,
        "actual_completion_tokens": 5,
        "actual_total_tokens": 15,
        "outcome_class": "succeeded",
        "observed_at": _now().isoformat(),
    }


def _event(*, payload: dict[str, object] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value}:"
            "work-1:attempt:1"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload=payload or _base_payload(),
        occurred_at=_now(),
        sequence_number=31,
    )


def test_projects_capacity_observed_to_versioned_envelope() -> None:
    projected = LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
        _event()
    )

    assert projected is not None
    assert projected.projection_version == 1
    assert projected.source_sequence_number == 31
    assert projected.projection_type == "workflow_capacity_window_observed"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
    assert projected.operation_key == "execute_claim_builder_section"
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["window_key"] == "groq:groq_org_primary:qwen/qwen3-32b"
    assert projected.payload["remaining_minute_requests"] == 2
    assert projected.payload["actual_total_tokens"] == 15


def test_reads_draft_claim_compaction_envelope_from_payload() -> None:
    projected = LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
        _event(
            payload=_base_payload(
                operation_key="execute_draft_claim_compaction",
                canonical_phase=(
                    KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
                ),
            )
        )
    )

    assert projected is not None
    assert projected.operation_key == "execute_draft_claim_compaction"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
    )


def test_projection_payload_uses_only_canonical_event_fields() -> None:
    projected = LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
        _event(
            payload={
                "workflow_run_id": _workflow_run_id(),
                "dispatch_attempt_id": "work-1:attempt:1",
                "work_item_id": "work-1",
                "operation_key": "execute_claim_builder_section",
                "canonical_phase": (
                    KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
                ),
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "outcome_class": "succeeded",
                "observed_at": _now().isoformat(),
            }
        )
    )

    assert projected is not None
    assert set(projected.payload) == {
        "workflow_run_id",
        "dispatch_attempt_id",
        "work_item_id",
        "window_key",
        "provider",
        "account_ref",
        "model_ref",
        "outcome_class",
        "observed_at",
    }


def test_documents_account_ref_exposure_risk_for_internal_admin_ui() -> None:
    projected = LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
        _event()
    )

    assert projected is not None
    assert projected.payload["account_ref"] == "groq_org_primary"


def test_ignores_unsupported_workflow_event() -> None:
    projected = LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
            workflow_run_id=_workflow_run_id(),
            payload={"workflow_run_id": _workflow_run_id()},
            occurred_at=_now(),
            sequence_number=1,
        )
    )

    assert projected is None


def test_requires_sequence_number() -> None:
    with pytest.raises(ValueError, match="sequence_number"):
        LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
            WorkflowEvent(
                event_id=WorkflowEventId("workflow-event:missing-sequence"),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value
                ),
                workflow_run_id=_workflow_run_id(),
                payload=_base_payload(),
                occurred_at=_now(),
            )
        )


@pytest.mark.parametrize("missing_key", ("operation_key", "canonical_phase"))
def test_requires_explicit_envelope_fields_in_payload(missing_key: str) -> None:
    payload = _base_payload()
    del payload[missing_key]

    with pytest.raises(ValueError, match=missing_key):
        LlmProviderCapacityObservedFrontendWorkflowEventProjector().project(
            _event(payload=payload)
        )

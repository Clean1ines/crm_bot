from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_dispatch_batch_frontend_workflow_event_projector import (
    ClaimBuilderDispatchBatchFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _event(*, source_unit_refs: tuple[str, ...] = ()) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            "ClaimBuilderDispatchBatchPrepared:2:work-1:attempt:1"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "prepared_dispatch_count": 2,
            "dispatch_attempt_ids": ("work-1:attempt:1", "work-2:attempt:1"),
            "work_item_ids": ("work-1", "work-2"),
            "input_size_preflight_decision": "USE_ACTIVE_MODEL",
            "input_size_preflight_reason": (
                "estimated prompt tokens fit active model input limit"
            ),
            "input_size_preflight_active_model_ref": "qwen/qwen3-32b",
            "source_split_required": False,
            "affected_work_item_refs": (),
            "source_unit_refs": source_unit_refs,
        },
        occurred_at=_now(),
        sequence_number=22,
    )


def test_projects_dispatch_batch_prepared_to_versioned_envelope() -> None:
    projected = ClaimBuilderDispatchBatchFrontendWorkflowEventProjector().project(
        _event()
    )

    assert projected is not None
    assert projected.projection_version == 1
    assert projected.source_sequence_number == 22
    assert projected.projection_type == "workflow_dispatch_batch_prepared"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
    assert projected.operation_key == "prepare_claim_builder_dispatch_batch"
    assert projected.project_id == "project-1"
    assert projected.document_id == "source-document:project-1:abc"
    assert projected.payload["prepared_dispatch_count"] == 2
    assert projected.payload["dispatch_attempt_ids"] == (
        "work-1:attempt:1",
        "work-2:attempt:1",
    )


def test_projection_payload_uses_only_canonical_event_fields() -> None:
    projected = ClaimBuilderDispatchBatchFrontendWorkflowEventProjector().project(
        _event(source_unit_refs=("unit-1", "unit-2"))
    )

    assert projected is not None
    assert set(projected.payload) == {
        "workflow_run_id",
        "work_kind",
        "prepared_dispatch_count",
        "dispatch_attempt_ids",
        "work_item_ids",
        "input_size_preflight_decision",
        "input_size_preflight_reason",
        "input_size_preflight_active_model_ref",
        "source_unit_refs",
    }


def test_projects_claim_builder_dispatch_attempt_prepared_overlay() -> None:
    parent = _event()
    event = WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{_workflow_run_id()}:"
            "ClaimBuilderDispatchAttemptPrepared:work-1:attempt:1"
        ),
        event_type=(
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value
        ),
        workflow_run_id=_workflow_run_id(),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": "source-document:project-1:abc",
            "source_unit_ref": "unit-1",
            "work_item_id": "work-1",
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "dispatch_attempt_id": "work-1:attempt:1",
            "attempt_number": 1,
            "attempt_state": "leased",
            "provider": "groq",
            "account_ref": "groq_org_primary",
            "model_ref": "qwen/qwen3-32b",
            "lease_expires_at": "2026-06-21T12:01:30+00:00",
        },
        occurred_at=parent.occurred_at,
        sequence_number=23,
    )

    projected = ClaimBuilderDispatchBatchFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert (
        projected.projection_type == "workflow_claim_builder_dispatch_attempt_prepared"
    )
    assert projected.payload["dispatch_attempt_id"] == "work-1:attempt:1"
    assert projected.payload["provider"] == "groq"
    assert projected.payload["account_ref"] == "groq_org_primary"
    assert projected.payload["attempt_state"] == "leased"


def test_ignores_unsupported_workflow_event() -> None:
    projected = ClaimBuilderDispatchBatchFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
            workflow_run_id="workflow-1",
            payload={},
            occurred_at=_now(),
            sequence_number=1,
        )
    )

    assert projected is None


def test_rejects_supported_event_without_source_sequence_number() -> None:
    event = _event()
    unpersisted = WorkflowEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        workflow_run_id=event.workflow_run_id,
        payload=event.payload,
        occurred_at=event.occurred_at,
    )

    with pytest.raises(ValueError, match="sequence_number is required"):
        ClaimBuilderDispatchBatchFrontendWorkflowEventProjector().project(unpersisted)

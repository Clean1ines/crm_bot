from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_section_outcome_frontend_workflow_event_projector import (
    ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _base_envelope_payload() -> dict[str, object]:
    return {
        "operation_key": "execute_claim_builder_section",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
        ),
    }


def _event(
    *,
    event_type: str,
    payload: dict[str, object],
    sequence_number: int = 41,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{_workflow_run_id()}:{event_type}:work-1:attempt:1"
        ),
        event_type=event_type,
        workflow_run_id=_workflow_run_id(),
        payload={**_base_envelope_payload(), **payload},
        occurred_at=_now(),
        sequence_number=sequence_number,
    )


def _extracted_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_ref": "unit-1",
        "dispatch_attempt_id": "work-1:attempt:1",
        "work_item_id": "work-1",
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "provider": "groq",
        "account_ref": "groq_org_primary",
        "model_ref": "qwen/qwen3-32b",
        "actual_total_tokens": 15,
        "persisted_draft_claim_count": 1,
        "validated_claim_count": 1,
        "validation_decision": "VALID_CLAIMS",
        "claim_builder_attempt_next_action_kind": "PERSIST_VALID_CLAIMS",
    }


def _item_owned_retryable_failed_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_ref": "unit-1",
        "dispatch_attempt_id": "work-1:attempt:1",
        "work_item_id": "work-1",
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "error_kind": "provider_error",
        "claim_builder_attempt_next_action_kind": "RETRY_SAME_MODEL",
        "claim_builder_attempt_next_action_reason": "provider_error",
        "validation_failure_reason": "INVALID_JSON_RETRY_REQUIRED",
        "retry_recommended": True,
    }


def _capacity_owned_retryable_failed_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_ref": "unit-1",
        "dispatch_attempt_id": "work-1:attempt:1",
        "work_item_id": "work-1",
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "error_kind": "minute_limit",
        "next_attempt_at": (_now() + timedelta(seconds=30)).isoformat(),
        "claim_builder_next_run_after": (_now() + timedelta(seconds=30)).isoformat(),
        "claim_builder_attempt_next_action_kind": "DEFER_UNTIL_CAPACITY_RESET",
        "claim_builder_attempt_next_action_reason": "minute_limit",
        "retry_recommended": True,
    }


def _terminal_failed_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_ref": "unit-1",
        "dispatch_attempt_id": "work-1:attempt:1",
        "work_item_id": "work-1",
        "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
        "error_kind": "claim_builder_output_validation_failed",
        "validation_failure_reason": "CLAIM_FIELD_SET_INVALID",
        "claim_builder_attempt_next_action_kind": "TERMINAL_FAILURE",
    }


def test_projects_extracted_to_versioned_envelope() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
            ),
            payload=_extracted_payload(),
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_section_extracted"
    assert projected.operation_key == "execute_claim_builder_section"
    assert (
        projected.canonical_phase
        == KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
    assert projected.payload["persisted_draft_claim_count"] == 1
    assert projected.payload["validated_claim_count"] == 1
    assert projected.payload["actual_total_tokens"] == 15
    assert projected.payload["work_item_state"] == "completed"
    assert projected.payload["dispatch_attempt_state"] == "completed"
    assert projected.payload["draft_claims_available"] is True
    assert (
        projected.payload["targeted_read_kind"]
        == "draft_claims_by_work_item_or_source_unit"
    )
    rows = projected.payload["draft_claim_observation_rows"]
    assert isinstance(rows, dict)
    assert rows["surface_kind"] == "draft_claim_observation"
    assert rows["availability"] == "available"
    assert rows["row_count"] == 1
    parent_scope = rows["parent_scope"]
    assert isinstance(parent_scope, dict)
    assert parent_scope == {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_ref": "unit-1",
        "work_item_id": "work-1",
        "dispatch_attempt_id": "work-1:attempt:1",
    }
    targeted_read = rows["targeted_read"]
    assert isinstance(targeted_read, dict)
    assert targeted_read["kind"] == "draft_claims_by_work_item_or_source_unit"
    assert targeted_read["params"] == {
        "workflow_run_id": _workflow_run_id(),
        "source_unit_ref": "unit-1",
        "work_item_id": "work-1",
        "dispatch_attempt_id": "work-1:attempt:1",
    }
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    assert attempt_outcome["attempt_scope"]["dispatch_attempt_id"] == (
        "work-1:attempt:1"
    )
    assert attempt_outcome["provider_outcome"]["provider_status"] == "succeeded"
    assert attempt_outcome["provider_outcome"]["actual_total_tokens"] == 15
    assert (
        attempt_outcome["validation_outcome"]["validation_status"]
        == "passed_valid_claims"
    )
    assert attempt_outcome["persistence_outcome"]["persistence_status"] == "persisted"
    assert attempt_outcome["targeted_read_hint"]["available"] is True
    assert (
        attempt_outcome["targeted_read_hint"]["targeted_read_kind"]
        == "draft_claims_by_work_item_or_source_unit"
    )
    assert attempt_outcome["work_item_outcome"]["final_work_item_status"] == "completed"


def test_projects_item_owned_retryable_failed_to_versioned_envelope() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=_item_owned_retryable_failed_payload(),
        )
    )

    assert projected is not None
    assert (
        projected.projection_type == "workflow_claim_builder_section_retryable_failed"
    )
    assert projected.payload["error_kind"] == "provider_error"
    assert projected.payload["claim_builder_attempt_next_action_kind"] == (
        "RETRY_SAME_MODEL"
    )
    assert "DEFER_UNTIL_CAPACITY_RESET" not in projected.payload.values()
    assert projected.payload["work_item_state"] == "retryable_failed"
    assert projected.payload["retry_driver"] == "capacity_window_admission"
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    assert attempt_outcome["provider_outcome"]["provider_status"] == "succeeded"
    assert (
        attempt_outcome["validation_outcome"]["validation_status"] == "failed_retryable"
    )
    assert (
        attempt_outcome["validation_outcome"]["validation_failure_reason"]
        == "INVALID_JSON_RETRY_REQUIRED"
    )
    assert (
        attempt_outcome["work_item_outcome"]["retry_eligibility"]
        == "eligible_for_future_admission"
    )
    assert (
        attempt_outcome["work_item_outcome"]["retry_driver"]
        == "capacity_window_admission"
    )


def test_capacity_owned_minute_limit_retryable_failed_is_not_projected() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=_capacity_owned_retryable_failed_payload(),
        )
    )

    assert projected is None


def test_capacity_owned_daily_reset_retryable_failed_is_not_projected() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload={
                **_capacity_owned_retryable_failed_payload(),
                "error_kind": "daily_limit",
                "claim_builder_attempt_next_action_kind": (
                    "PAUSE_FOR_DAILY_LIMIT_RESET"
                ),
                "claim_builder_attempt_next_action_reason": "daily_limit",
            },
        )
    )

    assert projected is None


def test_projects_terminal_failed_to_versioned_envelope() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED.value
            ),
            payload=_terminal_failed_payload(),
        )
    )

    assert projected is not None
    assert projected.projection_type == "workflow_claim_builder_section_terminal_failed"
    assert projected.payload["validation_failure_reason"] == "CLAIM_FIELD_SET_INVALID"
    assert projected.payload["work_item_state"] == "terminal_failed"
    assert projected.payload["retry_eligibility"] == "not_eligible"
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    assert (
        attempt_outcome["validation_outcome"]["validation_status"] == "failed_terminal"
    )
    assert (
        attempt_outcome["work_item_outcome"]["final_work_item_status"]
        == "terminal_failed"
    )
    assert attempt_outcome["work_item_outcome"]["retry_eligibility"] == "not_eligible"


def test_valid_empty_accepted_is_visible_as_attempt_outcome() -> None:
    payload = {
        **_extracted_payload(),
        "persisted_draft_claim_count": 0,
        "validated_claim_count": 0,
        "validation_decision": "VALID_EMPTY",
        "claim_builder_attempt_next_action_kind": "ACCEPT_VALID_EMPTY",
    }
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
            ),
            payload=payload,
        )
    )

    assert projected is not None
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    assert (
        attempt_outcome["validation_outcome"]["validation_status"]
        == "passed_valid_empty"
    )
    assert attempt_outcome["validation_outcome"]["valid_empty_accepted"] is True
    assert projected.payload["draft_claims_available"] is False
    assert "draft_claim_observation_rows" not in projected.payload
    assert "targeted_read_kind" not in projected.payload
    assert attempt_outcome["persistence_outcome"]["persistence_status"] == "skipped"
    assert attempt_outcome["persistence_outcome"]["draft_claims_available"] is False
    assert attempt_outcome["targeted_read_hint"]["available"] is False


def test_truncated_output_retry_is_visible_in_attempt_outcome() -> None:
    payload = {
        **_item_owned_retryable_failed_payload(),
        "error_kind": "claim_builder_output_validation_failed",
        "validation_failure_reason": "OUTPUT_TRUNCATED_RETRY_REQUIRED",
        "claim_builder_attempt_next_action_kind": "RETRY_LARGER_OUTPUT_LIMIT_MODEL",
        "claim_builder_attempt_next_action_reason": "output_truncated",
        "claim_builder_attempt_outcome_kind": "RETRY_LARGER_OUTPUT_LIMIT_MODEL",
    }
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=payload,
        )
    )

    assert projected is not None
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    assert attempt_outcome["provider_outcome"]["provider_status"] == "succeeded"
    assert (
        attempt_outcome["validation_outcome"]["validation_next_action"]
        == "RETRY_LARGER_OUTPUT_LIMIT_MODEL"
    )
    assert attempt_outcome["validation_outcome"]["output_truncated"] is True


def test_network_failure_is_provider_failure_with_passive_retryability() -> None:
    payload = {
        **_item_owned_retryable_failed_payload(),
        "error_kind": "network_error",
        "validation_failure_reason": None,
        "claim_builder_attempt_next_action_kind": "RETRY_SAME_MODEL",
        "claim_builder_attempt_next_action_reason": "network_error",
    }
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=payload,
        )
    )

    assert projected is not None
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    assert attempt_outcome["provider_outcome"]["provider_status"] == "failed"
    assert attempt_outcome["provider_outcome"]["provider_error_kind"] == "network_error"
    assert attempt_outcome["validation_outcome"]["validation_status"] == "not_run"
    assert (
        attempt_outcome["work_item_outcome"]["retry_eligibility"]
        == "eligible_for_future_admission"
    )


def test_attempt_outcome_excludes_forbidden_retry_timer_fields() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=_item_owned_retryable_failed_payload(),
        )
    )

    assert projected is not None
    attempt_outcome = projected.payload["attempt_outcome"]
    assert isinstance(attempt_outcome, dict)
    forbidden_keys = {
        "retry_owner",
        "work_item_retry_timer",
        "provider reset as item retry",
        "capacity_retry_at",
    }
    assert forbidden_keys.isdisjoint(attempt_outcome.keys())
    for nested_value in attempt_outcome.values():
        if isinstance(nested_value, dict):
            assert forbidden_keys.isdisjoint(nested_value.keys())


def test_retryable_and_terminal_outcomes_do_not_expose_draft_claim_rows() -> None:
    for event_type, payload in (
        (
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value,
            _item_owned_retryable_failed_payload(),
        ),
        (
            KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED.value,
            _terminal_failed_payload(),
        ),
    ):
        projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
            _event(event_type=event_type, payload=payload)
        )

        assert projected is not None
        assert "draft_claim_observation_rows" not in projected.payload
        assert "targeted_read_kind" not in projected.payload


def test_draft_claim_observation_rows_do_not_carry_claim_body_fields() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
            ),
            payload={
                **_extracted_payload(),
                "claim": "Do not project claim body",
                "possible_questions": ["Do not project questions"],
                "exclusion_scope": "Do not project exclusion scope",
                "evidence_block": "Do not project evidence block",
            },
        )
    )

    assert projected is not None
    rows = projected.payload["draft_claim_observation_rows"]
    assert isinstance(rows, dict)
    forbidden_body_fields = {
        "claim",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
    }
    assert forbidden_body_fields.isdisjoint(rows.keys())
    for value in rows.values():
        if isinstance(value, dict):
            assert forbidden_body_fields.isdisjoint(value.keys())


def test_deferred_event_type_is_not_projected() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED.value
            ),
            payload=_capacity_owned_retryable_failed_payload(),
        )
    )

    assert projected is None


def test_ignores_unsupported_workflow_event() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
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


@pytest.mark.parametrize("missing_key", ("operation_key", "canonical_phase"))
def test_requires_explicit_envelope_fields_in_payload(missing_key: str) -> None:
    payload = {**_base_envelope_payload(), **_extracted_payload()}
    del payload[missing_key]

    with pytest.raises(ValueError, match=missing_key):
        ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{_workflow_run_id()}:missing-envelope"
                ),
                event_type=(
                    KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
                ),
                workflow_run_id=_workflow_run_id(),
                payload=payload,
                occurred_at=_now(),
                sequence_number=41,
            )
        )


def test_item_owned_retryable_projection_excludes_capacity_timer_fields() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=_item_owned_retryable_failed_payload(),
        )
    )

    assert projected is not None
    for forbidden_key in (
        "next_attempt_at",
        "claim_builder_next_run_after",
        "minute_reset_at",
        "daily_reset_at",
        "remaining_minute_requests",
        "remaining_minute_tokens",
    ):
        assert forbidden_key not in projected.payload


def test_capacity_wait_belongs_to_capacity_window_not_item_projection() -> None:
    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
            ),
            payload=_capacity_owned_retryable_failed_payload(),
        )
    )

    assert projected is None


def _db_plain_event_type(value: str) -> str:
    return value.encode("utf-8").decode("utf-8")


def test_retryable_failed_event_type_loaded_from_db_plain_str_projects() -> None:
    enum_value = KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
    event_type = _db_plain_event_type(enum_value)

    assert event_type == enum_value
    assert event_type is not enum_value

    projected = ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector().project(
        _event(
            event_type=event_type,
            payload=_item_owned_retryable_failed_payload(),
        )
    )

    assert projected is not None
    assert (
        projected.projection_type == "workflow_claim_builder_section_retryable_failed"
    )
    assert projected.payload["work_item_state"] == "retryable_failed"

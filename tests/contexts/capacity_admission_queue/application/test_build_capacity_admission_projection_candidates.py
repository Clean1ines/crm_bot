import pytest
from typing import cast

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    BuildCapacityAdmissionProjectionCandidates,
    CapacityAdmissionLaneTarget,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


def _plan(
    *,
    payload: dict[str, object] | None = None,
) -> WorkItemSchedulePlan:
    return WorkItemSchedulePlan(
        work_item_id="work-item-1",
        work_kind=WorkKind("knowledge.claim_builder"),
        idempotency_key="idem-1",
        payload=payload
        or {
            "workflow_run_id": "workflow-run-1",
            "project_id": "project-1",
            "source_document_ref": "source-document-1",
            "source_unit_ref": "source-unit-1",
            "phase": "claim_builder",
            "llm_capacity_estimate": {
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 30,
            },
        },
    )


def test_builds_ready_projection_candidate_from_schedule_plan_and_lane_target() -> None:
    candidates = BuildCapacityAdmissionProjectionCandidates(
        lane_target=CapacityAdmissionLaneTarget(
            provider="groq",
            account_ref="groq-account-1",
            model_ref="llama-3.3-70b-versatile",
        )
    ).execute((_plan(),))

    assert len(candidates) == 1
    candidate = candidates[0]

    assert candidate.work_item_id == "work-item-1"
    assert candidate.work_kind == "knowledge.claim_builder"
    assert candidate.workflow_run_id == "workflow-run-1"
    assert candidate.project_id == "project-1"
    assert candidate.provider == "groq"
    assert candidate.account_ref == "groq-account-1"
    assert candidate.model_ref == "llama-3.3-70b-versatile"
    assert candidate.status is WorkItemStatus.READY
    assert candidate.retry_plan is None
    assert candidate.estimated_input_tokens == 100
    assert candidate.estimated_output_tokens == 30
    assert candidate.effective_output_cap_tokens == 30
    assert candidate.reserved_total_tokens == 130
    assert candidate.source_ref == {
        "workflow_run_id": "workflow-run-1",
        "project_id": "project-1",
        "source_document_ref": "source-document-1",
        "source_unit_ref": "source-unit-1",
        "phase": "claim_builder",
    }


def test_builds_projection_candidate_from_canonical_capacity_estimate_aliases() -> None:
    plan = _plan(
        payload={
            "workflow_run_id": "workflow-run-1",
            "llm_capacity_estimate": {
                "request_input_estimated_tokens": 100,
                "planned_output_reserve_tokens": 30,
                "request_total_estimated_tokens": 150,
            },
        }
    )

    candidates = BuildCapacityAdmissionProjectionCandidates(
        lane_target=CapacityAdmissionLaneTarget(
            provider="groq",
            model_ref="llama-3.3-70b-versatile",
        )
    ).execute((plan,))

    candidate = candidates[0]
    assert candidate.estimated_input_tokens == 100
    assert candidate.estimated_output_tokens == 30
    assert candidate.effective_output_cap_tokens == 30
    assert candidate.reserved_total_tokens == 150


def test_legacy_capacity_estimate_keys_take_precedence_over_canonical_aliases() -> None:
    plan = _plan(
        payload={
            "workflow_run_id": "workflow-run-1",
            "llm_capacity_estimate": {
                "estimated_input_tokens": 100,
                "request_input_estimated_tokens": 999,
                "estimated_output_tokens": 30,
                "planned_output_reserve_tokens": 999,
                "reserved_total_tokens": 130,
                "request_total_estimated_tokens": 999,
            },
        }
    )

    candidates = BuildCapacityAdmissionProjectionCandidates(
        lane_target=CapacityAdmissionLaneTarget(
            provider="groq",
            model_ref="llama-3.3-70b-versatile",
        )
    ).execute((plan,))

    candidate = candidates[0]
    assert candidate.estimated_input_tokens == 100
    assert candidate.estimated_output_tokens == 30
    assert candidate.reserved_total_tokens == 130


def test_uses_explicit_effective_output_cap_and_reserved_total_when_present() -> None:
    plan = _plan(
        payload={
            "workflow_run_id": "workflow-run-1",
            "llm_capacity_estimate": {
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 30,
                "effective_output_cap_tokens": 80,
                "reserved_total_tokens": 180,
            },
        }
    )

    candidates = BuildCapacityAdmissionProjectionCandidates(
        lane_target=CapacityAdmissionLaneTarget(
            provider="groq",
            model_ref="llama-3.3-70b-versatile",
        )
    ).execute((plan,))

    assert candidates[0].effective_output_cap_tokens == 80
    assert candidates[0].reserved_total_tokens == 180
    assert candidates[0].account_ref is None


def test_rejects_missing_capacity_estimate() -> None:
    plan = _plan(payload={"workflow_run_id": "workflow-run-1"})

    with pytest.raises(ValueError, match="llm_capacity_estimate"):
        BuildCapacityAdmissionProjectionCandidates(
            lane_target=CapacityAdmissionLaneTarget(
                provider="groq",
                model_ref="llama-3.3-70b-versatile",
            )
        ).execute((plan,))


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("estimated_input_tokens", 0),
        ("estimated_input_tokens", -1),
        ("estimated_input_tokens", True),
        ("estimated_output_tokens", -1),
        ("estimated_output_tokens", False),
        ("effective_output_cap_tokens", -1),
        ("reserved_total_tokens", 0),
    ),
)
def test_rejects_invalid_token_contract_values(
    field_name: str,
    bad_value: object,
) -> None:
    estimate: dict[str, object] = {
        "estimated_input_tokens": 100,
        "estimated_output_tokens": 30,
        "effective_output_cap_tokens": 30,
        "reserved_total_tokens": 130,
    }
    estimate[field_name] = bad_value
    plan = _plan(payload={"llm_capacity_estimate": estimate})

    with pytest.raises(ValueError, match=field_name):
        BuildCapacityAdmissionProjectionCandidates(
            lane_target=CapacityAdmissionLaneTarget(
                provider="groq",
                model_ref="llama-3.3-70b-versatile",
            )
        ).execute((plan,))


def test_rejects_effective_output_cap_lower_than_estimated_output() -> None:
    plan = _plan(
        payload={
            "llm_capacity_estimate": {
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 30,
                "effective_output_cap_tokens": 29,
                "reserved_total_tokens": 130,
            },
        }
    )

    with pytest.raises(ValueError, match="effective_output_cap_tokens"):
        BuildCapacityAdmissionProjectionCandidates(
            lane_target=CapacityAdmissionLaneTarget(
                provider="groq",
                model_ref="llama-3.3-70b-versatile",
            )
        ).execute((plan,))


def test_rejects_reserved_total_that_does_not_cover_input_and_output() -> None:
    plan = _plan(
        payload={
            "llm_capacity_estimate": {
                "estimated_input_tokens": 100,
                "estimated_output_tokens": 30,
                "reserved_total_tokens": 129,
            },
        }
    )

    with pytest.raises(ValueError, match="reserved_total_tokens"):
        BuildCapacityAdmissionProjectionCandidates(
            lane_target=CapacityAdmissionLaneTarget(
                provider="groq",
                model_ref="llama-3.3-70b-versatile",
            )
        ).execute((plan,))


def test_rejects_empty_lane_target_fields() -> None:
    with pytest.raises(ValueError, match="provider"):
        CapacityAdmissionLaneTarget(provider="", model_ref="llama-3.3-70b-versatile")

    with pytest.raises(ValueError, match="model_ref"):
        CapacityAdmissionLaneTarget(provider="groq", model_ref="")

    with pytest.raises(ValueError, match="account_ref"):
        CapacityAdmissionLaneTarget(
            provider="groq",
            model_ref="llama-3.3-70b-versatile",
            account_ref=" ",
        )


def test_rejects_non_schedule_plan_items() -> None:
    invalid_plans = _invalid_schedule_plan_sequence()

    with pytest.raises(TypeError, match="WorkItemSchedulePlan"):
        BuildCapacityAdmissionProjectionCandidates(
            lane_target=CapacityAdmissionLaneTarget(
                provider="groq",
                model_ref="llama-3.3-70b-versatile",
            )
        ).execute(invalid_plans)


def _invalid_schedule_plan_sequence() -> tuple[WorkItemSchedulePlan, ...]:
    return cast(tuple[WorkItemSchedulePlan, ...], ("not-a-plan",))

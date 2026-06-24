from __future__ import annotations

import pytest

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.llm_runtime.application.policies.request_output_cap_policy import (
    RequestOutputCapPolicy,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    groq_free_combined_tpm_output_cap_profile,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    _MutableInputCapacity,
    _admitted_schedule_payload,
    _input_admitted_candidates,
)


def _policy() -> RequestOutputCapPolicy:
    return RequestOutputCapPolicy(
        provider_profile=groq_free_combined_tpm_output_cap_profile(),
    )


def _account(*, remaining_tokens: int) -> _MutableInputCapacity:
    return _MutableInputCapacity(
        provider="groq",
        account_ref="groq_org_primary",
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=1,
        remaining_minute_tokens=remaining_tokens,
        remaining_daily_requests=100,
        remaining_daily_tokens=remaining_tokens,
    )


def _schedule_payload(
    *,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> dict[str, object]:
    return {
        "provider_messages": [{"role": "user", "content": "Extract claims"}],
        "llm_capacity_estimate": {
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_total_tokens": estimated_input_tokens + estimated_output_tokens,
        },
    }


def _record(
    work_item_id: str,
    *,
    status: WorkItemStatus = WorkItemStatus.READY,
    estimated_input_tokens: int,
    estimated_output_tokens: int = 1000,
) -> DueWorkItemRecord:
    return DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=WorkKind("knowledge.claim_builder"),
            status=status,
        ),
        schedule_payload=_schedule_payload(
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
        ),
    )


def test_admission_rejects_window_below_provider_default_output_cap() -> None:
    candidates = _input_admitted_candidates(
        due_records=(
            _record(
                "work-1",
                estimated_input_tokens=5000,
                estimated_output_tokens=1000,
            ),
        ),
        mutable_accounts=[_account(remaining_tokens=7047)],
        requested_items=1,
        hard_output_limit_tokens=8192,
        request_output_cap_policy=_policy(),
    )

    assert candidates == ()


def test_admission_accepts_window_covering_provider_default_output_cap() -> None:
    candidates = _input_admitted_candidates(
        due_records=(
            _record(
                "work-1",
                estimated_input_tokens=5000,
                estimated_output_tokens=1000,
            ),
        ),
        mutable_accounts=[_account(remaining_tokens=7048)],
        requested_items=1,
        hard_output_limit_tokens=8192,
        request_output_cap_policy=_policy(),
    )

    assert len(candidates) == 1
    assert candidates[0].request_output_cap_tokens is None
    assert candidates[0].effective_output_cap_tokens == 2048
    assert candidates[0].reserved_total_tokens == 7048


def test_admission_records_explicit_cap_when_safety_gap_fits() -> None:
    candidates = _input_admitted_candidates(
        due_records=(
            _record(
                "work-1",
                estimated_input_tokens=5000,
                estimated_output_tokens=1000,
            ),
        ),
        mutable_accounts=[_account(remaining_tokens=7348)],
        requested_items=1,
        hard_output_limit_tokens=8192,
        request_output_cap_policy=_policy(),
    )

    assert len(candidates) == 1
    assert candidates[0].request_output_cap_tokens == 2048
    assert candidates[0].effective_output_cap_tokens == 2048
    assert candidates[0].reserved_total_tokens == 7048


def test_retryable_no_fit_falls_through_to_ready_fit() -> None:
    candidates = _input_admitted_candidates(
        due_records=(
            _record(
                "retryable-high-input",
                status=WorkItemStatus.RETRYABLE_FAILED,
                estimated_input_tokens=6000,
                estimated_output_tokens=1000,
            ),
            _record(
                "ready-fitting-input",
                status=WorkItemStatus.READY,
                estimated_input_tokens=5000,
                estimated_output_tokens=1000,
            ),
        ),
        mutable_accounts=[_account(remaining_tokens=7048)],
        requested_items=1,
        hard_output_limit_tokens=8192,
        request_output_cap_policy=_policy(),
    )

    assert len(candidates) == 1
    assert candidates[0].record.work_item.work_item_id == "ready-fitting-input"


def test_admission_requires_estimated_output_tokens_not_legacy_reserved_output_tokens() -> (
    None
):
    legacy_schedule_payload = {
        "provider_messages": [{"role": "user", "content": "Extract claims"}],
        "llm_capacity_estimate": {
            "estimated_input_tokens": 5000,
            "reserved_output_tokens": 1000,
            "estimated_total_tokens": 6000,
        },
    }

    with pytest.raises(TypeError, match="estimated_output_tokens"):
        _input_admitted_candidates(
            due_records=(
                DueWorkItemRecord(
                    work_item=WorkItem(
                        work_item_id="legacy-work",
                        work_kind=WorkKind("knowledge.claim_builder"),
                        status=WorkItemStatus.READY,
                    ),
                    schedule_payload=legacy_schedule_payload,
                ),
            ),
            mutable_accounts=[_account(remaining_tokens=7048)],
            requested_items=1,
            hard_output_limit_tokens=8192,
            request_output_cap_policy=_policy(),
        )


def test_admitted_schedule_payload_carries_request_budget_fields() -> None:
    updated = _admitted_schedule_payload(
        schedule_payload=_schedule_payload(
            estimated_input_tokens=5000,
            estimated_output_tokens=1000,
        ),
        effective_output_cap_tokens=2048,
        request_output_cap_tokens=2048,
        reserved_total_tokens=7048,
    )

    estimate = updated["llm_capacity_estimate"]
    assert isinstance(estimate, dict)
    assert estimate["estimated_output_tokens"] == 1000
    assert "reserved_output_tokens" not in estimate
    assert estimate["effective_output_cap_tokens"] == 2048
    assert estimate["request_output_cap_tokens"] == 2048
    assert estimate["estimated_total_tokens"] == 7048
    assert estimate["reserved_total_tokens"] == 7048

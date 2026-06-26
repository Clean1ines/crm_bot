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
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparation,
    ClaimBuilderDispatchPreparationBuilder,
)


def _record(
    work_item_id: str,
    *,
    input_tokens: int,
    artifact_tokens: int,
) -> DueWorkItemRecord:
    return DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=WorkKind("knowledge.claim_builder"),
            status=WorkItemStatus.READY,
        ),
        schedule_payload={
            "llm_capacity_estimate": {
                "input_tokens": input_tokens,
                "artifact_tokens": artifact_tokens,
                "required_window_tokens": input_tokens + artifact_tokens,
            },
        },
    )


def test_profile_completion_estimate_comes_from_artifact_tokens() -> None:
    profile = (
        ClaimBuilderDispatchPreparationBuilder().build_profile_from_due_work_items(
            (
                _record(
                    "work-1",
                    input_tokens=5000,
                    artifact_tokens=1200,
                ),
                _record(
                    "work-2",
                    input_tokens=4000,
                    artifact_tokens=1600,
                ),
            ),
        )
    )

    assert profile.estimated_prompt_tokens == 5000
    assert profile.estimated_completion_tokens == 1600
    assert profile.estimated_requests == 1


def test_dispatch_preparation_payload_writes_canonical_profile_keys() -> None:
    preparation = ClaimBuilderDispatchPreparation(
        profile=LlmTaskCapacityProfile(
            profile_id="prompt-a",
            estimated_prompt_tokens=5000,
            estimated_completion_tokens=1600,
        ),
        account_capacities=(
            LlmProviderAccountCapacity(
                provider="groq",
                account_ref="groq_org_primary",
                model_ref="qwen/qwen3-32b",
                remaining_minute_requests=2,
                remaining_minute_tokens=7000,
                remaining_daily_requests=100,
                remaining_daily_tokens=50000,
            ),
        ),
        active_model_ref="qwen/qwen3-32b",
        requested_items=1,
    )

    payload = preparation.to_payload()
    profile = payload["profile"]

    assert isinstance(profile, dict)
    assert profile["input_tokens"] == 5000
    assert profile["artifact_tokens"] == 1600
    assert profile["estimated_prompt_tokens"] == 5000
    assert profile["estimated_completion_tokens"] == 1600
    assert "estimated_input_tokens" not in profile
    assert "estimated_output_tokens" not in profile


def test_profile_rejects_legacy_reserved_output_tokens_as_expected_output() -> None:
    legacy_record = DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id="legacy-work",
            work_kind=WorkKind("knowledge.claim_builder"),
            status=WorkItemStatus.READY,
        ),
        schedule_payload={
            "llm_capacity_estimate": {
                "input_tokens": 5000,
                "reserved_output_tokens": 1200,
                "required_window_tokens": 6200,
            },
        },
    )

    with pytest.raises(ValueError, match="artifact_tokens"):
        ClaimBuilderDispatchPreparationBuilder().build_profile_from_due_work_items(
            (legacy_record,),
        )

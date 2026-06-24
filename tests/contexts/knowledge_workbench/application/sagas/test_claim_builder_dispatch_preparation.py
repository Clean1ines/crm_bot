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
from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparationBuilder,
)


def _record(
    work_item_id: str,
    *,
    estimated_input_tokens: int,
    estimated_output_tokens: int,
) -> DueWorkItemRecord:
    return DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id=work_item_id,
            work_kind=WorkKind("knowledge.claim_builder"),
            status=WorkItemStatus.READY,
        ),
        schedule_payload={
            "llm_capacity_estimate": {
                "estimated_input_tokens": estimated_input_tokens,
                "estimated_output_tokens": estimated_output_tokens,
                "estimated_total_tokens": estimated_input_tokens
                + estimated_output_tokens,
            },
        },
    )


def test_profile_completion_estimate_comes_from_estimated_output_tokens() -> None:
    profile = (
        ClaimBuilderDispatchPreparationBuilder().build_profile_from_due_work_items(
            (
                _record(
                    "work-1",
                    estimated_input_tokens=5000,
                    estimated_output_tokens=1200,
                ),
                _record(
                    "work-2",
                    estimated_input_tokens=4000,
                    estimated_output_tokens=1600,
                ),
            ),
        )
    )

    assert profile.estimated_input_tokens == 5000
    assert profile.estimated_output_tokens == 1600
    assert profile.estimated_prompt_tokens == 5000
    assert profile.estimated_completion_tokens == 1600
    assert profile.estimated_requests == 1


def test_profile_rejects_legacy_reserved_output_tokens_as_expected_output() -> None:
    legacy_record = DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id="legacy-work",
            work_kind=WorkKind("knowledge.claim_builder"),
            status=WorkItemStatus.READY,
        ),
        schedule_payload={
            "llm_capacity_estimate": {
                "estimated_input_tokens": 5000,
                "reserved_output_tokens": 1200,
                "estimated_total_tokens": 6200,
            },
        },
    )

    with pytest.raises(ValueError, match="estimated_output_tokens"):
        ClaimBuilderDispatchPreparationBuilder().build_profile_from_due_work_items(
            (legacy_record,),
        )

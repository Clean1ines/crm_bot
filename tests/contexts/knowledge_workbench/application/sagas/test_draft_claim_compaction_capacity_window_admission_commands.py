from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.application.sagas.handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    _capacities_for_capacity_admission,
    _capacity_window_admission_pass_commands,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _payload_with_account_capacities() -> dict[str, object]:
    return {
        "workflow_run_id": "workflow-run-1",
        "scheduled_work_item_count": 2,
        "llm_dispatch_preparation": {
            "active_model_ref": "openai/gpt-oss-120b",
            "account_capacities": [
                {
                    "provider": "groq",
                    "account_ref": "groq_org_1",
                    "model_ref": "openai/gpt-oss-120b",
                    "remaining_minute_requests": 30,
                    "remaining_minute_tokens": 8000,
                    "remaining_daily_requests": 1000,
                    "remaining_daily_tokens": 200000,
                },
                {
                    "provider": "groq",
                    "account_ref": "groq_org_2",
                    "model_ref": "llama-3.3-70b-versatile",
                    "remaining_minute_requests": 30,
                    "remaining_minute_tokens": 12000,
                    "remaining_daily_requests": 1000,
                    "remaining_daily_tokens": 100000,
                },
                {
                    "provider": "groq",
                    "account_ref": "groq_org_3",
                    "model_ref": "openai/gpt-oss-120b",
                    "remaining_minute_requests": 30,
                    "remaining_minute_tokens": 8000,
                    "remaining_daily_requests": 1000,
                    "remaining_daily_tokens": 200000,
                },
            ],
        },
    }


def _workflow_command(payload: dict[str, object]) -> WorkflowCommand:
    now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:prepare-draft-compaction"),
        command_type="PrepareDraftClaimCompactionDispatchBatch",
        workflow_run_id="workflow-run-1",
        idempotency_key=WorkflowIdempotencyKey("prepare-draft-compaction"),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=now,
        created_at=now,
        updated_at=now,
    )


def test_draft_compaction_capacity_selection_returns_all_active_model_account_windows() -> (
    None
):
    capacities = _capacities_for_capacity_admission(_payload_with_account_capacities())

    assert [capacity["account_ref"] for capacity in capacities] == [
        "groq_org_1",
        "groq_org_3",
    ]
    assert {capacity["model_ref"] for capacity in capacities} == {"openai/gpt-oss-120b"}


def test_draft_compaction_admission_commands_are_built_for_each_active_model_window() -> (
    None
):
    payload = _payload_with_account_capacities()
    command = _workflow_command(payload)

    commands = _capacity_window_admission_pass_commands(
        workflow_command=command,
        workflow_run_id="workflow-run-1",
        occurred_at=command.updated_at,
    )

    assert len(commands) == 2
    assert [item.lane_key.account_ref for item in commands] == [
        "groq_org_1",
        "groq_org_3",
    ]
    assert {item.lane_key.model_ref for item in commands} == {"openai/gpt-oss-120b"}
    assert all(item.max_admitted_items == 2 for item in commands)

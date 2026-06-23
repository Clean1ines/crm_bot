from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemUserActionResolved,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    InvalidWorkItemTransition,
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


def _now() -> datetime:
    return datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _user_action_required_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("execution.test"),
        status=WorkItemStatus.USER_ACTION_REQUIRED,
        last_error_kind="needs_user_choice",
    )


def test_user_action_can_resolve_to_ready_without_retry_timer() -> None:
    resolved = WorkItemStateMachine.resolve_user_action_required_to_ready(
        _user_action_required_item(),
        reason="user_selected_wait",
    )

    assert resolved.status is WorkItemStatus.READY
    assert resolved.last_error_kind == "user_selected_wait"


def test_user_action_can_resolve_to_immediate_retryable_failed() -> None:
    resolved = WorkItemStateMachine.resolve_user_action_required_to_retryable_failed(
        _user_action_required_item(),
        reason="user_selected_continue",
    )

    assert resolved.status is WorkItemStatus.RETRYABLE_FAILED
    assert resolved.is_due(_now())


def test_user_action_resolution_rejects_non_user_action_item() -> None:
    ready = WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("execution.test"),
    )

    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.resolve_user_action_required_to_ready(ready)

    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.resolve_user_action_required_to_retryable_failed(ready)


def test_user_action_resolved_event_records_decision() -> None:
    event = WorkItemUserActionResolved(
        work_item_id="work-1",
        occurred_at=_now(),
        decision_kind="continue_with_degraded_model_or_resume_next_day",
        decision_value="continue_with_degraded_model",
    )

    assert event.work_item_id == "work-1"
    assert event.decision_kind == "continue_with_degraded_model_or_resume_next_day"
    assert event.decision_value == "continue_with_degraded_model"

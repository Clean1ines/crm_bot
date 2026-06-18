from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemUserActionResolved,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    InvalidWorkItemTransition,
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _user_action_required_item() -> WorkItem:
    now = _now()
    leased = WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )
    return WorkItemStateMachine.require_user_action_leased(
        leased,
        error_kind="daily_limit",
    )


def test_resolve_user_action_required_to_ready_requeues_work_item() -> None:
    item = _user_action_required_item()

    resolved = WorkItemStateMachine.resolve_user_action_required_to_ready(
        item,
        reason="continue_with_degraded_model",
    )

    assert resolved.status is WorkItemStatus.READY
    assert resolved.next_attempt_at is None
    assert resolved.last_error_kind == "continue_with_degraded_model"
    assert resolved.leased_by is None
    assert resolved.lease_token is None
    assert resolved.lease_expires_at is None


def test_resolve_user_action_required_to_retryable_failed_waits_until_reset() -> None:
    item = _user_action_required_item()
    wait_until = WaitUntil(_now() + timedelta(hours=12))

    resolved = WorkItemStateMachine.resolve_user_action_required_to_retryable_failed(
        item,
        wait_until=wait_until,
        reason="resume_after_daily_reset",
    )

    assert resolved.status is WorkItemStatus.RETRYABLE_FAILED
    assert resolved.next_attempt_at == wait_until
    assert resolved.last_error_kind == "resume_after_daily_reset"
    assert not resolved.is_due(_now())
    assert resolved.is_due(_now() + timedelta(hours=13))


def test_user_action_resolution_requires_user_action_required_item() -> None:
    ready = WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
    )

    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.resolve_user_action_required_to_ready(ready)

    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.resolve_user_action_required_to_retryable_failed(
            ready,
            wait_until=WaitUntil(_now() + timedelta(hours=12)),
        )


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

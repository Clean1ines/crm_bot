from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemUserActionRequired,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    InvalidWorkItemTransition,
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _leased_item() -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )


def test_user_action_required_status_is_terminal_for_automatic_execution() -> None:
    item = WorkItemStateMachine.require_user_action_leased(
        _leased_item(),
        error_kind="daily_limit",
    )

    assert item.status is WorkItemStatus.USER_ACTION_REQUIRED
    assert item.status.is_terminal
    assert not item.status.is_waiting
    assert item.last_error_kind == "daily_limit"
    assert item.leased_by is None
    assert item.lease_token is None
    assert item.lease_expires_at is None


def test_user_action_required_requires_leased_item() -> None:
    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.require_user_action_leased(
            WorkItem(
                work_item_id="work-1",
                work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            ),
            error_kind="daily_limit",
        )


def test_user_action_required_event_is_generic_execution_event() -> None:
    event = WorkItemUserActionRequired(
        work_item_id="work-1",
        occurred_at=_now(),
        decision_kind="continue_with_degraded_model_or_resume_next_day",
        reason="daily_limit",
    )

    assert event.work_item_id == "work-1"
    assert event.decision_kind == "continue_with_degraded_model_or_resume_next_day"
    assert event.reason == "daily_limit"

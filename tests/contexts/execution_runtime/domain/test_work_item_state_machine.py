from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    InvalidWorkItemTransition,
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _ready_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
    )


def _leased_item() -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        _ready_item(),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )


def _deferred_item() -> WorkItem:
    return WorkItemStateMachine.defer_leased(
        _leased_item(),
        wait_until=WaitUntil(_now() + timedelta(seconds=60)),
        error_kind="minute_limit",
    )


def _retryable_failed_item() -> WorkItem:
    return WorkItemStateMachine.fail_leased_retryable(
        _leased_item(),
        error_kind="network_timeout",
        next_attempt_at=WaitUntil(_now() + timedelta(seconds=10)),
    )


def _terminal_failed_item() -> WorkItem:
    return WorkItemStateMachine.fail_leased_terminal(
        _leased_item(),
        error_kind="invalid_payload",
    )


def test_work_item_statuses_are_canonical_and_business_agnostic() -> None:
    assert {status.value for status in WorkItemStatus} == {
        "ready",
        "leased",
        "deferred",
        "completed",
        "retryable_failed",
        "terminal_failed",
        "cancelled",
        "split_superseded",
        "user_action_required",
    }

    forbidden_legacy_statuses = {
        "claim_observations_persisted",
        "registry_application_queued",
        "registry_application_applied",
        "waiting_for_fresh_registry",
    }

    assert forbidden_legacy_statuses.isdisjoint(
        {status.value for status in WorkItemStatus}
    )


def test_legacy_deferred_status_is_not_waiting_and_never_due() -> None:
    legacy_deferred = WorkItem(
        work_item_id="legacy-deferred-work",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=WorkItemStatus.DEFERRED,
        next_attempt_at=WaitUntil(_now() - timedelta(seconds=1)),
        last_error_kind="legacy_capacity_wait",
    )

    assert WorkItemStatus.DEFERRED.is_waiting is False
    assert legacy_deferred.is_due(_now()) is False


def test_lease_ready_item_sets_lease_fields_and_increments_attempt_count() -> None:
    now = _now()
    leased = WorkItemStateMachine.lease_ready(
        _ready_item(),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )

    assert leased.status is WorkItemStatus.LEASED
    assert leased.attempt_count == 1
    assert leased.leased_by == WorkerRef("worker-1")
    assert leased.lease_token == LeaseToken("lease-1")
    assert leased.has_active_lease(now)


def test_complete_requires_leased_item_and_clears_lease_fields() -> None:
    leased = _leased_item()

    completed = WorkItemStateMachine.complete_leased(leased)

    assert completed.status is WorkItemStatus.COMPLETED
    assert completed.leased_by is None
    assert completed.lease_token is None
    assert completed.lease_expires_at is None

    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.complete_leased(_ready_item())


def test_defer_leased_item_marks_retryable_with_wait_until_and_clears_lease() -> None:
    leased = _leased_item()
    wait_until = WaitUntil(_now() + timedelta(seconds=60))

    deferred = WorkItemStateMachine.defer_leased(
        leased,
        wait_until=wait_until,
        error_kind="minute_limit",
    )

    assert deferred.status is WorkItemStatus.RETRYABLE_FAILED
    assert deferred.next_attempt_at == wait_until
    assert deferred.last_error_kind == "minute_limit"
    assert deferred.retry_plan is WorkItemRetryPlan.WAIT_NEAREST_CAPACITY_WINDOW
    assert deferred.leased_by is None
    assert deferred.lease_token is None
    assert not deferred.is_due(_now())
    assert deferred.is_due(_now() + timedelta(seconds=61))


def test_retryable_and_terminal_failures_are_explicit_transitions() -> None:
    leased = _leased_item()

    retryable = WorkItemStateMachine.fail_leased_retryable(
        leased,
        error_kind="network_timeout",
        next_attempt_at=WaitUntil(_now() + timedelta(seconds=10)),
        retry_plan=WorkItemRetryPlan.RETRY_OTHER_ORG,
    )

    assert retryable.status is WorkItemStatus.RETRYABLE_FAILED
    assert retryable.last_error_kind == "network_timeout"
    assert retryable.next_attempt_at == WaitUntil(_now() + timedelta(seconds=10))
    assert retryable.retry_plan is WorkItemRetryPlan.RETRY_OTHER_ORG

    terminal = WorkItemStateMachine.fail_leased_terminal(
        leased,
        error_kind="invalid_work_payload",
    )

    assert terminal.status is WorkItemStatus.TERMINAL_FAILED
    assert terminal.last_error_kind == "invalid_work_payload"
    assert terminal.next_attempt_at is None


def test_cancel_clears_lease_and_marks_item_terminal() -> None:
    cancelled = WorkItemStateMachine.cancel(
        _leased_item(), error_kind="cancelled_by_user"
    )

    assert cancelled.status is WorkItemStatus.CANCELLED
    assert cancelled.status.is_terminal
    assert cancelled.last_error_kind == "cancelled_by_user"
    assert cancelled.leased_by is None
    assert cancelled.lease_token is None

    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.cancel(cancelled)


def test_split_superseded_is_not_fake_completed_empty_success() -> None:
    superseded = WorkItemStateMachine.mark_split_superseded_leased(_leased_item())

    assert superseded.status is WorkItemStatus.SPLIT_SUPERSEDED
    assert superseded.status.is_terminal


def test_reclaim_expired_lease_returns_work_to_ready_without_attempt_increment() -> (
    None
):
    now = _now()
    leased = WorkItemStateMachine.lease_ready(
        _ready_item(),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )

    unchanged = WorkItemStateMachine.reclaim_expired_lease(
        leased,
        now=now + timedelta(seconds=29),
    )
    assert unchanged is leased

    reclaimed = WorkItemStateMachine.reclaim_expired_lease(
        leased,
        now=now + timedelta(seconds=30),
    )

    assert reclaimed.status is WorkItemStatus.READY
    assert reclaimed.attempt_count == 1
    assert reclaimed.last_error_kind == "lease_expired"
    assert reclaimed.leased_by is None
    assert reclaimed.lease_token is None
    assert reclaimed.lease_expires_at is None


def test_mark_split_superseded_waiting_accepts_ready_item() -> None:
    superseded = WorkItemStateMachine.mark_split_superseded_waiting(_ready_item())

    assert superseded.status is WorkItemStatus.SPLIT_SUPERSEDED
    assert superseded.status.is_terminal
    assert superseded.leased_by is None
    assert superseded.lease_token is None
    assert superseded.lease_expires_at is None
    assert superseded.next_attempt_at is None
    assert superseded.last_error_kind is None


def test_mark_split_superseded_waiting_accepts_retryable_capacity_wait_item() -> None:
    superseded = WorkItemStateMachine.mark_split_superseded_waiting(_deferred_item())

    assert superseded.status is WorkItemStatus.SPLIT_SUPERSEDED
    assert superseded.next_attempt_at is None
    assert superseded.last_error_kind is None


def test_mark_split_superseded_waiting_accepts_retryable_failed_item() -> None:
    superseded = WorkItemStateMachine.mark_split_superseded_waiting(
        _retryable_failed_item(),
    )

    assert superseded.status is WorkItemStatus.SPLIT_SUPERSEDED
    assert superseded.next_attempt_at is None
    assert superseded.last_error_kind is None


@pytest.mark.parametrize(
    "item",
    (
        _leased_item(),
        WorkItemStateMachine.complete_leased(_leased_item()),
        _terminal_failed_item(),
        WorkItemStateMachine.cancel(_ready_item()),
        WorkItemStateMachine.mark_split_superseded_leased(_leased_item()),
        WorkItemStateMachine.require_user_action_leased(
            _leased_item(),
            error_kind="needs_user_choice",
        ),
    ),
)
def test_mark_split_superseded_waiting_rejects_non_waiting_statuses(
    item: WorkItem,
) -> None:
    with pytest.raises(InvalidWorkItemTransition):
        WorkItemStateMachine.mark_split_superseded_waiting(item)


def test_existing_leased_split_supersede_transition_still_works() -> None:
    superseded = WorkItemStateMachine.mark_split_superseded_leased(_leased_item())

    assert superseded.status is WorkItemStatus.SPLIT_SUPERSEDED
    assert superseded.status.is_terminal

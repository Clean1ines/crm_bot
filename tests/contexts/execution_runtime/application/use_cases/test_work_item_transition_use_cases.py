from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.use_cases.cancel_work_item import (
    CancelWorkItemCommand,
)
from src.contexts.execution_runtime.application.use_cases.fail_work_item import (
    FailWorkItemCommand,
    WorkItemFailureMode,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef


ROOT = Path(__file__).resolve().parents[5]


def _now() -> datetime:
    return datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)


def _leased_item() -> WorkItem:
    return WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("execution.test"),
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=_now() + timedelta(minutes=5),
        now=_now(),
    )


def test_fail_retryable_command_no_longer_requires_work_item_retry_timer() -> None:
    command = FailWorkItemCommand(
        item=_leased_item(),
        mode=WorkItemFailureMode.RETRYABLE,
        error_kind="network_error",
        occurred_at=_now(),
    )

    assert command.mode is WorkItemFailureMode.RETRYABLE


def test_retryable_failure_state_is_immediate_retry_queue() -> None:
    failed = WorkItemStateMachine.fail_leased_retryable(
        _leased_item(),
        error_kind="network_error",
    )

    assert failed.status is WorkItemStatus.RETRYABLE_FAILED
    assert failed.is_due(_now())


def test_transition_sources_do_not_use_removed_work_item_retry_timing() -> None:
    for rel in (
        "src/contexts/execution_runtime/application/use_cases/fail_work_item.py",
        "src/contexts/execution_runtime/domain/state_machines/work_item_state_machine.py",
    ):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "next" + "_attempt" + "_at" not in source


def test_commands_reject_blank_reasons() -> None:
    with pytest.raises(ValueError):
        FailWorkItemCommand(
            item=_leased_item(),
            mode=WorkItemFailureMode.RETRYABLE,
            error_kind="",
            occurred_at=_now(),
        )

    with pytest.raises(ValueError):
        CancelWorkItemCommand(
            item=_leased_item(),
            reason="",
            occurred_at=_now(),
        )

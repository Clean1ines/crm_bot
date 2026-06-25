from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.contexts.capacity_admission_queue.application.sync_capacity_admission_projection_lifecycle import (
    CapacityAdmissionProjectionLifecycleUpdate,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_projection_lifecycle_synchronizer import (
    PostgresCapacityAdmissionProjectionLifecycleSynchronizer,
)


@dataclass(frozen=True, slots=True)
class FetchRowCall:
    query: str
    args: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class ExecuteCall:
    query: str
    args: tuple[object, ...]


class FakeConnection:
    def __init__(self, row: Mapping[str, object] | None) -> None:
        self.row = row
        self.fetchrow_calls: list[FetchRowCall] = []
        self.execute_calls: list[ExecuteCall] = []

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.fetchrow_calls.append(FetchRowCall(query=query, args=args))
        return self.row

    async def execute(self, query: str, *args: object) -> object:
        self.execute_calls.append(ExecuteCall(query=query, args=args))
        return "INSERT 0 1"


def _changed_at() -> datetime:
    return datetime(2026, 6, 24, 18, 0, tzinfo=timezone.utc)


def _row(
    *,
    previous_status: str = "leased",
    status: str = "retryable_failed",
    retry_plan: str | None = "RETRY_SAME_ROUTE",
    account_ref: str | None = "groq-account-1",
    model_ref: str = "llama-3.3-70b-versatile",
) -> Mapping[str, object]:
    return {
        "work_item_id": "work-item-1",
        "work_kind": "knowledge.claim_builder",
        "provider": "groq",
        "account_ref": account_ref,
        "model_ref": model_ref,
        "previous_status": previous_status,
        "status": status,
        "retry_plan": retry_plan,
    }


@pytest.mark.asyncio
async def test_syncs_leased_to_retryable_failed_and_emits_due_wakeup() -> None:
    connection = FakeConnection(_row())

    result = await PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
        connection
    ).sync_projection_lifecycle(
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="retryable_failed",
            retry_plan="RETRY_SAME_ROUTE",
            changed_at=_changed_at(),
        )
    )

    assert result is not None
    assert result.work_item_id == "work-item-1"
    assert result.previous_status == "leased"
    assert result.status == "retryable_failed"
    assert result.retry_plan == "RETRY_SAME_ROUTE"
    assert result.event_type == "DueWorkQueueChanged"
    assert result.reason == "work_item_returned_retryable"
    assert isinstance(result.event_id, UUID)

    update_call = connection.fetchrow_calls[0]
    assert "UPDATE capacity_admission_work_items" in update_call.query
    assert "status = $2" in update_call.query
    assert "retry_plan = $3" in update_call.query
    assert "model_ref = COALESCE($5, work_items.model_ref)" in update_call.query
    assert "FOR UPDATE" in update_call.query
    assert update_call.args == (
        "work-item-1",
        "retryable_failed",
        "RETRY_SAME_ROUTE",
        _changed_at(),
        None,
    )

    dirty_call = connection.execute_calls[0]
    assert "INSERT INTO capacity_admission_lane_dirty_flags" in dirty_call.query
    assert dirty_call.args[0] == (
        "knowledge.claim_builder:groq:groq-account-1:llama-3.3-70b-versatile"
    )
    assert dirty_call.args[5] == "work_item_returned_retryable"

    event_call = connection.execute_calls[1]
    assert "INSERT INTO capacity_admission_lane_events" in event_call.query
    assert event_call.args[2] == "DueWorkQueueChanged"
    assert event_call.args[8] == "work_item_returned_retryable"
    payload = json.loads(str(event_call.args[9]))
    assert payload == {
        "model_ref": "llama-3.3-70b-versatile",
        "previous_status": "leased",
        "retry_plan": "RETRY_SAME_ROUTE",
        "status": "retryable_failed",
        "work_item_id": "work-item-1",
    }


@pytest.mark.asyncio
async def test_retryable_failed_can_move_projection_to_retry_model_lane() -> None:
    connection = FakeConnection(_row(model_ref="llama-3.3-70b-versatile"))

    result = await PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
        connection
    ).sync_projection_lifecycle(
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="retryable_failed",
            retry_plan="retry_larger_output_limit_route",
            model_ref="llama-3.3-70b-versatile",
            changed_at=_changed_at(),
        )
    )

    assert result is not None
    assert result.lane_key.model_ref == "llama-3.3-70b-versatile"
    update_call = connection.fetchrow_calls[0]
    assert update_call.args == (
        "work-item-1",
        "retryable_failed",
        "retry_larger_output_limit_route",
        _changed_at(),
        "llama-3.3-70b-versatile",
    )


@pytest.mark.asyncio
async def test_syncs_terminal_status_as_capacity_window_wakeup() -> None:
    connection = FakeConnection(
        _row(
            status="completed",
            retry_plan=None,
        )
    )

    result = await PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
        connection
    ).sync_projection_lifecycle(
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="completed",
            changed_at=_changed_at(),
        )
    )

    assert result is not None
    assert result.status == "completed"
    assert result.retry_plan is None
    assert result.event_type == "CapacityWindowChanged"
    assert result.reason == "attempt_finished_capacity_available"

    event_call = connection.execute_calls[1]
    assert event_call.args[2] == "CapacityWindowChanged"
    assert event_call.args[8] == "attempt_finished_capacity_available"


@pytest.mark.asyncio
async def test_uses_null_safe_lane_id_for_missing_account_ref() -> None:
    connection = FakeConnection(_row(account_ref=None))

    result = await PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
        connection
    ).sync_projection_lifecycle(
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="retryable_failed",
            retry_plan="RETRY_SAME_ROUTE",
            changed_at=_changed_at(),
        )
    )

    assert result is not None
    assert result.lane_key.account_ref is None
    dirty_call = connection.execute_calls[0]
    assert dirty_call.args[0] == (
        "knowledge.claim_builder:groq:-:llama-3.3-70b-versatile"
    )


@pytest.mark.asyncio
async def test_returns_none_when_projection_row_is_missing_or_already_synced() -> None:
    connection = FakeConnection(row=None)

    result = await PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
        connection
    ).sync_projection_lifecycle(
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="completed",
            changed_at=_changed_at(),
        )
    )

    assert result is None
    assert len(connection.fetchrow_calls) == 1
    assert connection.execute_calls == []


def test_rejects_retryable_failed_without_retry_plan() -> None:
    with pytest.raises(ValueError, match="retry_plan"):
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="retryable_failed",
            changed_at=_changed_at(),
        )


def test_rejects_retry_plan_for_terminal_status() -> None:
    with pytest.raises(ValueError, match="retry_plan"):
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="completed",
            retry_plan="RETRY_SAME_ROUTE",
            changed_at=_changed_at(),
        )


def test_rejects_model_ref_for_terminal_status() -> None:
    with pytest.raises(ValueError, match="model_ref"):
        CapacityAdmissionProjectionLifecycleUpdate(
            work_item_id="work-item-1",
            status="completed",
            model_ref="llama-3.3-70b-versatile",
            changed_at=_changed_at(),
        )

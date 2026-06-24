from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLease,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_projection_admitter import (
    PostgresCapacityAdmissionProjectionAdmitter,
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


def _now() -> datetime:
    return datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _lane(account_ref: str | None = "groq-account-1") -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge.claim_builder",
        provider="groq",
        account_ref=account_ref,
        model_ref="llama-3.3-70b-versatile",
    )


def _lease(
    account_ref: str | None = "groq-account-1",
) -> CapacityAdmissionProjectionLease:
    return CapacityAdmissionProjectionLease(
        work_item_id="work-item-1",
        lane_key=_lane(account_ref=account_ref),
        leased_at=_now(),
    )


def _row(*, previous_status: str = "ready") -> Mapping[str, object]:
    return {
        "work_item_id": "work-item-1",
        "work_kind": "knowledge.claim_builder",
        "provider": "groq",
        "account_ref": "groq-account-1",
        "model_ref": "llama-3.3-70b-versatile",
        "previous_status": previous_status,
        "status": "leased",
    }


@pytest.mark.asyncio
async def test_marks_ready_projection_row_as_leased_and_appends_lane_event() -> None:
    connection = FakeConnection(_row(previous_status="ready"))

    result = await PostgresCapacityAdmissionProjectionAdmitter(
        connection
    ).admit_projection_work_item(_lease())

    assert result is not None
    assert result.work_item_id == "work-item-1"
    assert result.previous_status == "ready"
    assert result.status == "leased"
    assert result.lane_key == _lane()
    assert isinstance(result.event_id, UUID)

    update_call = connection.fetchrow_calls[0]
    assert "UPDATE capacity_admission_work_items" in update_call.query
    assert "status = 'leased'" in update_call.query
    assert "status IN ('ready', 'retryable_failed')" in update_call.query
    assert "RETURNING" in update_call.query
    assert update_call.args == (
        "work-item-1",
        _now(),
        "knowledge.claim_builder",
        "groq",
        "groq-account-1",
        "llama-3.3-70b-versatile",
    )

    event_call = connection.execute_calls[0]
    assert "INSERT INTO capacity_admission_lane_events" in event_call.query
    assert "CapacityWindowLeasedWorkItem" in event_call.query
    assert event_call.args[1] == (
        "knowledge.claim_builder:groq:groq-account-1:llama-3.3-70b-versatile"
    )
    assert event_call.args[7] == "capacity_window_admitted"
    assert event_call.args[8] == _now()


@pytest.mark.asyncio
async def test_marks_retryable_failed_projection_row_as_leased() -> None:
    connection = FakeConnection(_row(previous_status="retryable_failed"))

    result = await PostgresCapacityAdmissionProjectionAdmitter(
        connection
    ).admit_projection_work_item(_lease())

    assert result is not None
    assert result.previous_status == "retryable_failed"
    assert result.status == "leased"
    assert len(connection.execute_calls) == 1


@pytest.mark.asyncio
async def test_returns_none_when_row_was_already_taken_or_terminal() -> None:
    connection = FakeConnection(row=None)

    result = await PostgresCapacityAdmissionProjectionAdmitter(
        connection
    ).admit_projection_work_item(_lease())

    assert result is None
    assert len(connection.fetchrow_calls) == 1
    assert connection.execute_calls == []


@pytest.mark.asyncio
async def test_uses_null_safe_account_ref_filter() -> None:
    row = dict(_row())
    row["account_ref"] = None
    connection = FakeConnection(row)

    result = await PostgresCapacityAdmissionProjectionAdmitter(
        connection
    ).admit_projection_work_item(_lease(account_ref=None))

    assert result is not None
    assert result.lane_key.account_ref is None
    update_call = connection.fetchrow_calls[0]
    assert "account_ref IS NOT DISTINCT FROM $5" in update_call.query
    assert update_call.args[4] is None
    event_call = connection.execute_calls[0]
    assert event_call.args[1] == (
        "knowledge.claim_builder:groq:-:llama-3.3-70b-versatile"
    )


@pytest.mark.asyncio
async def test_rejects_malformed_returning_row() -> None:
    row = dict(_row())
    row["previous_status"] = "leased"
    connection = FakeConnection(row)

    with pytest.raises(ValueError, match="previous_status"):
        await PostgresCapacityAdmissionProjectionAdmitter(
            connection
        ).admit_projection_work_item(_lease())

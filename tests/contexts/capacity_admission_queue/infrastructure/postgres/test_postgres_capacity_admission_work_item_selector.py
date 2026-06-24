from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import pytest

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_work_item_selector import (
    PostgresCapacityAdmissionWorkItemSelector,
)


@dataclass(frozen=True, slots=True)
class FetchRowCall:
    query: str
    args: tuple[object, ...]


class FakeConnection:
    def __init__(
        self,
        row: Mapping[str, object] | None = None,
    ) -> None:
        self.row = row
        self.fetchrow_calls: list[FetchRowCall] = []

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.fetchrow_calls.append(FetchRowCall(query=query, args=args))
        return self.row


def _lane(account_ref: str | None = "groq-account-1") -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge.claim_builder",
        provider="groq",
        account_ref=account_ref,
        model_ref="llama-3.3-70b-versatile",
    )


def _row(
    *,
    work_item_id: str = "work-item-1",
    status: str = "ready",
    account_ref: str | None = "groq-account-1",
    reserved_total_tokens: int = 130,
) -> Mapping[str, object]:
    return {
        "work_item_id": work_item_id,
        "work_kind": "knowledge.claim_builder",
        "provider": "groq",
        "account_ref": account_ref,
        "model_ref": "llama-3.3-70b-versatile",
        "status": status,
        "reserved_total_tokens": reserved_total_tokens,
    }


@pytest.mark.asyncio
async def test_selects_first_retryable_failed_fit_with_skip_locked_query() -> None:
    connection = FakeConnection(
        _row(status="retryable_failed", reserved_total_tokens=130)
    )

    selected = await PostgresCapacityAdmissionWorkItemSelector(
        connection
    ).select_first_retryable_failed_fit(
        lane_key=_lane(),
        max_reserved_total_tokens=4096,
    )

    assert selected is not None
    assert selected.work_item_id == "work-item-1"
    assert selected.status == "retryable_failed"
    assert selected.reserved_total_tokens == 130
    assert selected.lane_key == _lane()

    call = connection.fetchrow_calls[0]
    assert "FROM capacity_admission_work_items" in call.query
    assert "status = $5" in call.query
    assert "reserved_total_tokens <= $6" in call.query
    assert "ORDER BY updated_at ASC, work_item_id ASC" in call.query
    assert "LIMIT 1" in call.query
    assert "FOR UPDATE SKIP LOCKED" in call.query
    assert call.args == (
        "knowledge.claim_builder",
        "groq",
        "groq-account-1",
        "llama-3.3-70b-versatile",
        "retryable_failed",
        4096,
    )


@pytest.mark.asyncio
async def test_selects_first_ready_fit_with_same_lane_filter() -> None:
    connection = FakeConnection(_row(status="ready", reserved_total_tokens=1024))

    selected = await PostgresCapacityAdmissionWorkItemSelector(
        connection
    ).select_first_ready_fit(
        lane_key=_lane(),
        max_reserved_total_tokens=2048,
    )

    assert selected is not None
    assert selected.status == "ready"
    assert selected.reserved_total_tokens == 1024
    call = connection.fetchrow_calls[0]
    assert call.args == (
        "knowledge.claim_builder",
        "groq",
        "groq-account-1",
        "llama-3.3-70b-versatile",
        "ready",
        2048,
    )


@pytest.mark.asyncio
async def test_uses_is_not_distinct_from_for_absent_account_ref() -> None:
    connection = FakeConnection(_row(status="ready", account_ref=None))

    selected = await PostgresCapacityAdmissionWorkItemSelector(
        connection
    ).select_first_ready_fit(
        lane_key=_lane(account_ref=None),
        max_reserved_total_tokens=2048,
    )

    assert selected is not None
    assert selected.lane_key.account_ref is None
    call = connection.fetchrow_calls[0]
    assert "account_ref IS NOT DISTINCT FROM $3" in call.query
    assert call.args[2] is None


@pytest.mark.asyncio
async def test_returns_none_when_no_fitting_row_exists() -> None:
    connection = FakeConnection(row=None)

    selected = await PostgresCapacityAdmissionWorkItemSelector(
        connection
    ).select_first_ready_fit(
        lane_key=_lane(),
        max_reserved_total_tokens=2048,
    )

    assert selected is None
    assert len(connection.fetchrow_calls) == 1


@pytest.mark.asyncio
async def test_rejects_non_positive_token_fit_limit() -> None:
    with pytest.raises(ValueError, match="max_reserved_total_tokens"):
        await PostgresCapacityAdmissionWorkItemSelector(
            FakeConnection()
        ).select_first_ready_fit(
            lane_key=_lane(),
            max_reserved_total_tokens=0,
        )


@pytest.mark.asyncio
async def test_rejects_unexpected_projection_status_from_database() -> None:
    connection = FakeConnection(_row(status="leased"))

    with pytest.raises(ValueError, match="unsupported capacity admission status"):
        await PostgresCapacityAdmissionWorkItemSelector(
            connection
        ).select_first_ready_fit(
            lane_key=_lane(),
            max_reserved_total_tokens=2048,
        )


def _invalid_row_missing_work_item_id() -> Mapping[str, object]:
    row = dict(_row())
    row.pop("work_item_id")
    return row


@pytest.mark.asyncio
async def test_rejects_malformed_database_row() -> None:
    connection = FakeConnection(_invalid_row_missing_work_item_id())

    with pytest.raises(ValueError, match="work_item_id"):
        await PostgresCapacityAdmissionWorkItemSelector(
            connection
        ).select_first_ready_fit(
            lane_key=_lane(),
            max_reserved_total_tokens=2048,
        )
